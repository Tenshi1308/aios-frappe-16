"""Integration tests for the Telegram channel connector (needs a site).

Covers C5/C6/C7/C8/C10/C11/C13: one reply per update, identity is the configured
recipient (never `Administrator`), the site quota gates the channel, no ERPNext write
happens, flags are created by rules and closed by a human, notifications reach
all active channel recipients (with fallback to active client owners), and the poll
offset is durable.
"""

from unittest.mock import patch

import frappe

from aios_v1.lib import draft_manager
from aios_v1.lib.connector import dispatch, notify, poller, rules, telegram_client, views

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

SETTING = "AIOS Telegram Setting"
THREAD = "AIOS Channel Thread"
FLAG = "AIOS Conversation Flag"
OWNER = "_test.connector.owner@example.com"
SECOND_RECEIVER = "_test.connector.receiver2@example.com"
OTHER = "_test.connector.other@example.com"
CHAT_ID = "99001122"
CHAT_ID_B = "99003344"

DRF_00080_MARKDOWN_REPLY = (
    "Baik, Kak Tenshi! Terima kasih atas konfirmasinya. 😊 Sebentar, saya cek dulu tanggalnya untuk memastikan jadwal pengiriman yang tepat.\n\n"
    "Baik, Kak Tenshi! Terima kasih atas konfirmasinya. 😊 Saya buatkan **draf pesanan**-nya sekarang ya.\n\n"
    "Baik, Kak Tenshi! Terima kasih atas konfirmasinya. 😊 Draf pesanan Anda sudah saya buatkan ya.\n\n"
    "## ✅ Draf Pesanan Berhasil Dibuat\n\n"
    "| Item | Qty | Harga Satuan | Subtotal |\n"
    "|---|---|---|---|\n"
    "| Kabel Jaringan Cat6 UTP 100 Meter (CBL-CAT6-100) | 1 pcs | Rp 850.000 | **Rp 850.000** |\n\n"
    "💰 **Harga Dasar:** Rp 850.000\n"
    "🧾 **PPN 11%:** Rp 93.500\n"
    "💰 **Total: Rp 943.500**\n\n"
    "### 📋 Data Pelanggan (Perorangan)\n"
    "- **Nama:** Tenshi\n"
    "- **No. HP:** 08123456789\n"
    "- **Alamat:** Jalan Sukabumi No. 50, **Bandung**\n"
    "- **Tanggal Pengiriman:** **15 November 2026**\n\n"
    "### 💳 Metode Pembayaran\n"
    "- **Cash (Tunai)** — pembayaran dikonfirmasi terlebih dahulu sebelum pesanan dikirim\n\n"
    "### 📌 Status\n"
    "- **Nomor Referensi:** DRF-2026-11-00080\n"
    "- **Status:** Menunggu persetujuan tim kami untuk diproses lebih lanjut\n\n"
    "Tim kami akan segera menghubungi Kak Tenshi di **08123456789** untuk konfirmasi dan langkah selanjutnya (termasuk pembayaran & pengiriman).\n\n"
    "Apakah ada lagi yang bisa saya bantu? 😊"
)


def _ensure_user(email: str, name: str, extra_roles: list[str] | None = None) -> str:
    roles = [{"role": "AIOS Client"}]
    for role in extra_roles or []:
        if role != "AIOS Client":
            roles.append({"role": role})
    if not frappe.db.exists("User", email):
        doc = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": name,
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "Website User",
                "aios_status": "Active",
                "roles": roles,
            }
        )
        doc.insert(ignore_permissions=True)
    else:
        frappe.db.set_value(
            "User",
            email,
            {"enabled": 1, " user_type": "Website User", "aios_status": "Active"}
            if False
            else {"enabled": 1, "user_type": "Website User", "aios_status": "Active"},
            update_modified=False,
        )
        for item in roles:
            r = item["role"]
            if not frappe.db.exists("Has Role", {"parent": email, "parenttype": "User", "role": r}):
                frappe.get_doc(
                    {
                        "doctype": "Has Role",
                        "parent": email,
                        "parenttype": "User",
                        "parentfield": "roles",
                        "role": r,
                    }
                ).insert(ignore_permissions=True)
    frappe.clear_cache(user=email)
    return email


class ConnectorTestBase(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.in_test = True
        frappe.flags.in_test = True
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self.addCleanup(self._restore_and_rollback)
        frappe.set_user("Administrator")
        frappe.db.set_value("AIOS Setting", "AIOS Setting", "max_users", 20, update_modified=False)
        frappe.db.delete(
            "Has Role",
            {"parenttype": "User", "role": ("in", ["AIOS Channel Receiver", "AIOS Client Owner"])},
        )
        self.owner = _ensure_user(OWNER, "Connector Owner", extra_roles=["AIOS Channel Receiver"])
        self.other = _ensure_user(OTHER, "Connector Other")
        self._orig_active = frappe.db.get_single_value(SETTING, "is_active")
        frappe.db.set_value(SETTING, SETTING, "is_active", 1)
        frappe.db.set_value(SETTING, SETTING, "poll_offset", 0)
        dispatch.clear_rate_limit(CHAT_ID)
        dispatch.clear_rate_limit(CHAT_ID_B)
        self._cleanup_threads()

    def _restore_and_rollback(self):
        frappe.set_user("Administrator")
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        frappe.set_user("Administrator")
        self._cleanup_threads()
        dispatch.clear_rate_limit(CHAT_ID)
        dispatch.clear_rate_limit(CHAT_ID_B)
        for email in (OWNER, OTHER, SECOND_RECEIVER):
            for cname in frappe.get_all("Contact", filters={"user": email}, pluck="name"):
                frappe.delete_doc("Contact", cname, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("Notification Settings", email):
                frappe.delete_doc("Notification Settings", email, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, ignore_permissions=True, force=True, delete_permanently=True)
        frappe.db.set_value(SETTING, SETTING, "is_active", self._orig_active)
        frappe.db.set_value(SETTING, SETTING, "poll_offset", 0)
        self._restore_and_rollback()
        super().tearDown()

    def _cleanup_threads(self):
        for name in frappe.get_all(
            THREAD, filters={"external_thread_id": ("in", [CHAT_ID, CHAT_ID_B])}, pluck="name"
        ):
            for flag in frappe.get_all(FLAG, filters={"thread": name}, pluck="name"):
                frappe.delete_doc(FLAG, flag, ignore_permissions=True, force=True, delete_permanently=True)
            conversation = frappe.db.get_value(THREAD, name, "conversation")
            frappe.delete_doc(THREAD, name, ignore_permissions=True, force=True, delete_permanently=True)
            if conversation and frappe.db.exists("AIOS Conversation", conversation):
                frappe.delete_doc("AIOS Conversation", conversation, ignore_permissions=True, force=True, delete_permanently=True)

    def _update(self, text: str, update_id: int = 1, chat_id: str | int | None = None) -> dict:
        return {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "chat": {"id": int(chat_id if chat_id is not None else CHAT_ID)},
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
        self.assertEqual(thread.owner, self.owner)
        self.assertEqual(thread.channel, "telegram")
        self.assertEqual(thread.external_thread_id, CHAT_ID)
        conversation = frappe.get_doc("AIOS Conversation", thread.conversation)
        self.assertEqual(conversation.branch, "sales")
        # In Batch 2, unlinked guest thread conversation belongs to Guest
        self.assertEqual(conversation.user, "Guest")

    def test_identity_is_owner_not_administrator(self):
        """C6: the chat path reads frappe.session.user, so it must be Guest (or linked_user), never Administrator."""
        seen = {}

        def fake_reply(manager, conversation, effective_user, text):
            seen["session"] = frappe.session.user
            return "ok"

        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", side_effect=fake_reply):
            dispatch.process_update(self._update("halo"))

        self.assertEqual(seen["session"], "Guest")
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

    def test_two_chats_get_separate_conversations(self):
        """R1-a: dua chat_id tidak boleh berbagi satu AIOS Conversation."""
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", return_value="ok"):
            res_a = dispatch.process_update(self._update("halo A", 1, chat_id=CHAT_ID))
            res_b = dispatch.process_update(self._update("halo B", 2, chat_id=CHAT_ID_B))

        self.assertTrue(res_a["success"])
        self.assertTrue(res_b["success"])
        thread_a = frappe.db.get_value(THREAD, {"external_thread_id": CHAT_ID}, "conversation")
        thread_b = frappe.db.get_value(THREAD, {"external_thread_id": CHAT_ID_B}, "conversation")
        self.assertTrue(thread_a, "thread A harus memiliki conversation")
        self.assertTrue(thread_b, "thread B harus memiliki conversation")
        self.assertNotEqual(thread_a, thread_b, "dua chat_id berbeda harus mendapat conversation berbeda")

    def test_messages_of_chat_a_do_not_leak_into_transcript_of_chat_b(self):
        """R1-b: pesan dari chat A tidak boleh muncul di transkrip chat B."""
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", return_value="jawaban bot"):
            dispatch.process_update(self._update("rahasia chat A", 1, chat_id=CHAT_ID))
            dispatch.process_update(self._update("pertanyaan chat B", 2, chat_id=CHAT_ID_B))

        thread_b = frappe.get_doc(THREAD, {"external_thread_id": CHAT_ID_B})
        transcript_b = dispatch._transcript(thread_b.conversation)
        contents_b = [msg.get("content") for msg in transcript_b]
        self.assertNotIn("rahasia chat A", contents_b, "pesan chat A tidak boleh ada di percakapan B")

    def test_missing_owner_fails_closed(self):
        frappe.db.delete(
            "Has Role",
            {"parenttype": "User", "role": ("in", ["AIOS Channel Receiver", "AIOS Client Owner"])},
        )
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

    def test_markdown_reply_converted_to_plain_text_preserving_all_content(self):
        plain = dispatch.format_telegram_plain_text(DRF_00080_MARKDOWN_REPLY)

        for marker in ("##", "###", "**", "|---|", "`"):
            self.assertNotIn(marker, plain)

        for expected_text in (
            "✅ Draf Pesanan Berhasil Dibuat",
            "- Item — Qty — Harga Satuan — Subtotal",
            "- Kabel Jaringan Cat6 UTP 100 Meter (CBL-CAT6-100) — 1 pcs — Rp 850.000 — Rp 850.000",
            "💰 Harga Dasar: Rp 850.000",
            "🧾 PPN 11%: Rp 93.500",
            "💰 Total: Rp 943.500",
            "📋 Data Pelanggan (Perorangan)",
            "- Nama: Tenshi",
            "- No. HP: 08123456789",
            "- Alamat: Jalan Sukabumi No. 50, Bandung",
            "- Tanggal Pengiriman: 15 November 2026",
            "💳 Metode Pembayaran",
            "- Cash (Tunai) — pembayaran dikonfirmasi terlebih dahulu sebelum pesanan dikirim",
            "📌 Status",
            "- Nomor Referensi: DRF-2026-11-00080",
            "- Status: Menunggu persetujuan tim kami untuk diproses lebih lanjut",
            "Tim kami akan segera menghubungi Kak Tenshi di 08123456789",
            "Apakah ada lagi yang bisa saya bantu? 😊",
        ):
            self.assertIn(expected_text, plain)
        self.assertNotIn("(belum termasuk pajak/PPN)", plain)

        extra_md = (
            "Lihat [Panduan](https://example.com/panduan) untuk `DRF-2026-11-00080` "
            "(*penting* dan _catatan_), bukan _Test_Identifier atau confirm_cash_payment."
        )
        plain_extra = dispatch.format_telegram_plain_text(extra_md)
        self.assertEqual(
            plain_extra,
            "Lihat Panduan (https://example.com/panduan) untuk DRF-2026-11-00080 "
            "(penting dan catatan), bukan _Test_Identifier atau confirm_cash_payment.",
        )

    def test_markdown_reply_split_into_ordered_bubbles_and_respects_max_length(self):
        plain = dispatch.format_telegram_plain_text(DRF_00080_MARKDOWN_REPLY)
        bubbles = dispatch.split_telegram_bubbles(plain)

        self.assertEqual(len(bubbles), 11)
        self.assertEqual("\n\n".join(bubbles), plain)
        self.assertEqual(bubbles[3], "✅ Draf Pesanan Berhasil Dibuat")
        self.assertEqual(
            bubbles[4],
            "- Item — Qty — Harga Satuan — Subtotal\n"
            "- Kabel Jaringan Cat6 UTP 100 Meter (CBL-CAT6-100) — 1 pcs — Rp 850.000 — Rp 850.000",
        )
        self.assertTrue(bubbles[6].startswith("📋 Data Pelanggan (Perorangan)\n"))
        self.assertIn("- Tanggal Pengiriman: 15 November 2026", bubbles[6])
        self.assertTrue(bubbles[8].startswith("📌 Status\n"))
        self.assertEqual(bubbles[-1], "Apakah ada lagi yang bisa saya bantu? 😊")

        # Bagian > 4096 karakter dipecah aman pada batas baris/kalimat tanpa melebihi batas Telegram
        long_bullets = "\n".join(
            f"- Item {idx:03d}: Kabel Jaringan Cat6 UTP Outdoor Berkualitas Tinggi 100m"
            for idx in range(1, 90)
        )
        long_paragraph = " ".join(
            f"Kalimat konfirmasi ke-{idx:03d} memastikan seluruh detail pesanan pelanggan tercatat lengkap."
            for idx in range(1, 70)
        )
        long_text = f"{long_bullets}\n\n{long_paragraph}"
        self.assertGreater(len(long_bullets), dispatch.TELEGRAM_MAX_MESSAGE_LENGTH)
        self.assertGreater(len(long_paragraph), dispatch.TELEGRAM_MAX_MESSAGE_LENGTH)

        long_bubbles = dispatch.split_telegram_bubbles(long_text)
        self.assertGreater(len(long_bubbles), 2)
        for bubble in long_bubbles:
            self.assertLessEqual(len(bubble), dispatch.TELEGRAM_MAX_MESSAGE_LENGTH)
        # Tidak memotong di tengah satu poin daftar maupun di tengah kalimat panjang
        bullet_bubbles = [b for b in long_bubbles if b.startswith("- Item ")]
        self.assertGreaterEqual(len(bullet_bubbles), 2)
        self.assertEqual("\n".join(bullet_bubbles), long_bullets)
        sentence_bubbles = [b for b in long_bubbles if b.startswith("Kalimat konfirmasi ke-")]
        self.assertGreaterEqual(len(sentence_bubbles), 2)
        self.assertEqual(" ".join(sentence_bubbles), long_paragraph)

    def test_plain_text_and_single_part_reply_unchanged_and_single_bubble(self):
        plain_reply = (
            "Stok Kabel Jaringan Cat6 UTP 100 Meter tersedia 25 pcs (Rp 850.000). "
            "Silakan konfirmasi detail pesanan Anda."
        )
        self.assertEqual(dispatch.format_telegram_plain_text(plain_reply), plain_reply)

        sent: list[tuple[str, str]] = []
        with patch.object(
            telegram_client,
            "send_message",
            side_effect=lambda cid, txt: sent.append((str(cid), txt)) or True,
        ), patch.object(telegram_client, "send_chat_action", return_value=True), patch.object(
            dispatch, "_collect_reply", return_value=plain_reply
        ):
            res = dispatch.process_update(self._update("Cek stok kabel Cat6"))

        self.assertTrue(res["success"])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1], plain_reply)

    def test_process_update_sends_plain_bubbles_to_telegram_while_aios_message_keeps_raw_markdown(self):
        sent: list[tuple[str, str]] = []

        def markdown_llm(messages, usage=None, tools=None, tool_calls=None):
            yield DRF_00080_MARKDOWN_REPLY

        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=markdown_llm), patch.object(
            telegram_client, "send_chat_action", return_value=True
        ), patch.object(
            telegram_client,
            "send_message",
            side_effect=lambda cid, txt: sent.append((str(cid), txt)) or True,
        ):
            res = dispatch.process_update(self._update("Ya, tolong buatkan draf pesanan saya"))

        self.assertTrue(res["success"])
        expected_plain = dispatch.format_telegram_plain_text(DRF_00080_MARKDOWN_REPLY)
        expected_bubbles = dispatch.split_telegram_bubbles(expected_plain)
        self.assertEqual(len(sent), len(expected_bubbles))
        self.assertEqual(len(sent), 11)
        self.assertEqual([txt for _, txt in sent], expected_bubbles)
        for _, txt in sent:
            for marker in ("##", "###", "**", "|---|", "`"):
                self.assertNotIn(marker, txt)

        # AIOS Message yang tersimpan di DB (dipakai Ekasa Desk) tetap markdown asli
        saved_manager_msgs = frappe.get_all(
            "AIOS Message",
            filters={"conversation": res["conversation"], "role": "manager"},
            fields=["content"],
            order_by="creation asc",
        )
        self.assertEqual(len(saved_manager_msgs), 1)
        stored_content = saved_manager_msgs[0]["content"]
        self.assertEqual(stored_content, DRF_00080_MARKDOWN_REPLY)
        self.assertIn("## ✅ Draf Pesanan Berhasil Dibuat", stored_content)
        self.assertIn("| Item | Qty | Harga Satuan | Subtotal |", stored_content)
        self.assertIn("**Rp 850.000**", stored_content)


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
        self.assertEqual(flag.owner, self.owner)
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
        """C11: the notification reaches the active recipient and nobody else."""
        self.assertTrue(notify.ensure_notification_type())
        thread = self._make_thread()
        flag = frappe.get_all(FLAG, filters={"thread": thread}, pluck="name")[0]
        try:
            flag_doc = frappe.get_doc(FLAG, flag)
            notify.notify_flag(flag_doc)
            rows = frappe.get_all(
                "Notification Log", filters={"document_name": flag}, fields=["for_user"]
            )
            self.assertEqual([row["for_user"] for row in rows], [self.owner])
        finally:
            for name in frappe.get_all("Notification Log", filters={"document_name": flag}, pluck="name"):
                frappe.delete_doc("Notification Log", name, ignore_permissions=True, force=True)

    def test_multiple_receivers_both_get_flag_and_order_notifications(self):
        """Keputusan 2 & 4: dua pemegang Role AIOS Channel Receiver aktif keduanya menerima notifikasi."""
        self.assertTrue(notify.ensure_notification_type())
        receiver2 = _ensure_user(SECOND_RECEIVER, "Second Receiver", extra_roles=["AIOS Channel Receiver"])
        self.assertEqual(sorted(notify.get_channel_recipients()), sorted([self.owner, receiver2]))

        thread = self._make_thread()
        flag = frappe.get_all(FLAG, filters={"thread": thread}, pluck="name")[0]
        draft_doc = draft_manager.create_draft(
            task_id="task-multi-1",
            action_type="CREATE",
            branch="sales",
            created_by_agent="sales",
            payload={"doctype": "Sales Order", "data": {"customer": "Budi", "items": [{"item_code": "ITEM-1", "qty": 2}]}},
            user=self.owner,
        )
        try:
            flag_doc = frappe.get_doc(FLAG, flag)
            self.assertTrue(notify.notify_flag(flag_doc))
            flag_users = frappe.get_all(
                "Notification Log", filters={"document_name": flag}, pluck="for_user"
            )
            self.assertEqual(sorted(flag_users), sorted([self.owner, receiver2]))

            self.assertTrue(
                notify.notify_order_draft(
                    draft_doc,
                    thread={"display_name": "Budi", "external_thread_id": CHAT_ID},
                )
            )
            draft_users = frappe.get_all(
                "Notification Log", filters={"document_name": draft_doc.name}, pluck="for_user"
            )
            self.assertEqual(sorted(draft_users), sorted([self.owner, receiver2]))
        finally:
            for docname in [flag, draft_doc.name]:
                for n in frappe.get_all("Notification Log", filters={"document_name": docname}, pluck="name"):
                    frappe.delete_doc("Notification Log", n, ignore_permissions=True, force=True)
            frappe.delete_doc("Pending Action Draft", draft_doc.name, ignore_permissions=True, force=True)

    def test_fallback_to_client_owner_when_no_receiver_and_stops_when_receiver_added(self):
        """Keputusan 6: fallback ke AIOS Client Owner aktif bila belum ada AIOS Channel Receiver."""
        frappe.db.delete(
            "Has Role",
            {"parenttype": "User", "role": ("in", ["AIOS Channel Receiver", "AIOS Client Owner"])},
        )
        owner_only = _ensure_user(OWNER, "Connector Owner", extra_roles=["AIOS Client Owner"])
        self.assertEqual(notify.get_channel_recipients(), [owner_only])

        # Begitu ada 1 pemegang AIOS Channel Receiver aktif, fallback berhenti:
        receiver2 = _ensure_user(SECOND_RECEIVER, "Second Receiver", extra_roles=["AIOS Channel Receiver"])
        self.assertEqual(notify.get_channel_recipients(), [receiver2])

    def test_channel_draft_accessible_to_second_receiver_but_not_regular_client(self):
        """Keputusan 13 (Opsi A): draf pesanan kanal dapat dibuka & ditindaklanjuti oleh penerima ke-2."""
        self.assertTrue(notify.ensure_notification_type())
        receiver2 = _ensure_user(SECOND_RECEIVER, "Second Receiver", extra_roles=["AIOS Channel Receiver"])
        draft_doc = draft_manager.create_draft(
            task_id="task-opt-a-1",
            action_type="CREATE",
            branch="sales",
            created_by_agent="sales",
            payload={"doctype": "Sales Order", "data": {"customer": "Budi", "items": [{"item_code": "ITEM-1", "qty": 1}]}},
            user=self.owner,
        )
        try:
            notify.notify_order_draft(
                draft_doc,
                thread={"display_name": "Budi", "external_thread_id": CHAT_ID},
            )
            # User AIOS Client biasa (bukan penerima) ditolak membaca draf kanal:
            frappe.set_user(self.other)
            with self.assertRaises(frappe.PermissionError):
                draft_manager.get_draft(draft_doc.name)

            # Penerima ke-2 (AIOS Channel Receiver aktif) diizinkan membaca & menolak draf kanal:
            frappe.set_user(receiver2)
            fetched = draft_manager.get_draft(draft_doc.name)
            self.assertEqual(fetched["name"], draft_doc.name)
            rejected = draft_manager.reject_draft(draft_doc.name, reason="Stok habis")
            self.assertEqual(rejected["status"], "success")
            self.assertEqual(frappe.db.get_value("Pending Action Draft", draft_doc.name, "status"), "REJECTED")
        finally:
            frappe.set_user("Administrator")
            for n in frappe.get_all("Notification Log", filters={"document_name": draft_doc.name}, pluck="name"):
                frappe.delete_doc("Notification Log", n, ignore_permissions=True, force=True)
            frappe.delete_doc("Pending Action Draft", draft_doc.name, ignore_permissions=True, force=True)

    def _make_thread(self) -> str:
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", return_value="ok"), \
             patch.object(dispatch, "notify_flag", return_value=True):
            return dispatch.process_update(self._update("transfer ke rekening pribadi"))["thread"]

    def test_notification_type_exists_after_migrate(self):
        self.assertTrue(frappe.db.exists("Notification Type", notify.NOTIFICATION_TYPE))

    def test_linked_receiver_gets_telegram_push_on_flag_and_unlinked_is_skipped(self):
        """Linked active receiver gets concise Telegram push on flag; unlinked & guest chat are skipped."""
        self.assertTrue(notify.ensure_notification_type())
        receiver2 = _ensure_user(SECOND_RECEIVER, "Second Receiver", extra_roles=["AIOS Channel Receiver"])
        guest_thread = self._make_thread()
        flag_name = frappe.get_all(FLAG, filters={"thread": guest_thread}, pluck="name")[0]
        flag_doc = frappe.get_doc(FLAG, flag_name)

        # Link self.owner to a separate employee Telegram thread; leave receiver2 unlinked.
        emp_conv = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.owner, "branch": "sales"}
        ).insert(ignore_permissions=True)
        emp_thread = frappe.get_doc(
            {
                "doctype": "AIOS Channel Thread",
                "channel": "telegram",
                "external_thread_id": CHAT_ID_B,
                "conversation": emp_conv.name,
                "linked_user": self.owner,
                "linked_at": frappe.utils.now_datetime(),
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        try:
            with patch("aios_v1.lib.connector.telegram_client.send_message", return_value=True) as mock_send:
                self.assertTrue(notify.notify_flag(flag_doc))

            # Bell/email Notification Log still created for both active receivers.
            flag_users = frappe.get_all("Notification Log", filters={"document_name": flag_name}, pluck="for_user")
            self.assertEqual(sorted(flag_users), sorted([self.owner, receiver2]))

            # Telegram push only sent to linked employee chat_id (never guest CHAT_ID or unlinked receiver2).
            mock_send.assert_called_once()
            sent_chat_id, sent_text = mock_send.call_args.args
            self.assertEqual(str(sent_chat_id), CHAT_ID_B)
            self.assertNotEqual(str(sent_chat_id), CHAT_ID)
            self.assertIn("Flag", sent_text)
            self.assertIn(flag_doc.label, sent_text)
            self.assertIn("Peringatan Kanal", sent_text)
        finally:
            for n in frappe.get_all("Notification Log", filters={"document_name": flag_name}, pluck="name"):
                frappe.delete_doc("Notification Log", n, ignore_permissions=True, force=True)
            frappe.delete_doc(THREAD, emp_thread.name, ignore_permissions=True, force=True)
            frappe.delete_doc("AIOS Conversation", emp_conv.name, ignore_permissions=True, force=True)

    def test_telegram_failure_on_flag_logs_and_keeps_bell_notification(self):
        """Telegram send failure or exception logs error and never blocks Notification Log or return True."""
        self.assertTrue(notify.ensure_notification_type())
        guest_thread = self._make_thread()
        flag_name = frappe.get_all(FLAG, filters={"thread": guest_thread}, pluck="name")[0]
        flag_doc = frappe.get_doc(FLAG, flag_name)

        emp_conv = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.owner, "branch": "sales"}
        ).insert(ignore_permissions=True)
        emp_thread = frappe.get_doc(
            {
                "doctype": "AIOS Channel Thread",
                "channel": "telegram",
                "external_thread_id": CHAT_ID_B,
                "conversation": emp_conv.name,
                "linked_user": self.owner,
                "linked_at": frappe.utils.now_datetime(),
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        try:
            with patch("aios_v1.lib.connector.telegram_client.send_message", return_value=False) as mock_send, \
                 patch.object(notify, "log_exception") as mock_log:
                self.assertTrue(notify.notify_flag(flag_doc))
            mock_send.assert_called_once()
            mock_log.assert_called()
            flag_users = frappe.get_all("Notification Log", filters={"document_name": flag_name}, pluck="for_user")
            self.assertEqual(flag_users, [self.owner])

            for n in frappe.get_all("Notification Log", filters={"document_name": flag_name}, pluck="name"):
                frappe.delete_doc("Notification Log", n, ignore_permissions=True, force=True)

            with patch("aios_v1.lib.connector.telegram_client.send_message", side_effect=RuntimeError("tg down")), \
                 patch.object(notify, "log_exception") as mock_log:
                self.assertTrue(notify.notify_flag(flag_doc))
            mock_log.assert_called()
            flag_users = frappe.get_all("Notification Log", filters={"document_name": flag_name}, pluck="for_user")
            self.assertEqual(flag_users, [self.owner])
        finally:
            for n in frappe.get_all("Notification Log", filters={"document_name": flag_name}, pluck="name"):
                frappe.delete_doc("Notification Log", n, ignore_permissions=True, force=True)
            frappe.delete_doc(THREAD, emp_thread.name, ignore_permissions=True, force=True)
            frappe.delete_doc("AIOS Conversation", emp_conv.name, ignore_permissions=True, force=True)

    def test_fallback_client_owner_linked_gets_telegram_and_empty_excerpt_safe(self):
        """Fallback AIOS Client Owner linked to Telegram gets flag push; empty excerpt prints cleanly."""
        self.assertTrue(notify.ensure_notification_type())
        frappe.db.delete(
            "Has Role",
            {"parenttype": "User", "role": ("in", ["AIOS Channel Receiver", "AIOS Client Owner"])},
        )
        owner_only = _ensure_user(OWNER, "Connector Owner", extra_roles=["AIOS Client Owner"])
        guest_thread = self._make_thread()
        flag_name = frappe.get_all(FLAG, filters={"thread": guest_thread}, pluck="name")[0]
        flag_doc = frappe.get_doc(FLAG, flag_name)
        flag_doc.excerpt = None

        emp_conv = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": owner_only, "branch": "sales"}
        ).insert(ignore_permissions=True)
        emp_thread = frappe.get_doc(
            {
                "doctype": "AIOS Channel Thread",
                "channel": "telegram",
                "external_thread_id": CHAT_ID_B,
                "conversation": emp_conv.name,
                "linked_user": owner_only,
                "linked_at": frappe.utils.now_datetime(),
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        try:
            with patch("aios_v1.lib.connector.telegram_client.send_message", return_value=True) as mock_send:
                self.assertTrue(notify.notify_flag(flag_doc))
            mock_send.assert_called_once()
            sent_chat_id, sent_text = mock_send.call_args.args
            self.assertEqual(str(sent_chat_id), CHAT_ID_B)
            self.assertNotIn("None", sent_text)
            self.assertIn("Peringatan Kanal", sent_text)
        finally:
            for n in frappe.get_all("Notification Log", filters={"document_name": flag_name}, pluck="name"):
                frappe.delete_doc("Notification Log", n, ignore_permissions=True, force=True)
            frappe.delete_doc(THREAD, emp_thread.name, ignore_permissions=True, force=True)
            frappe.delete_doc("AIOS Conversation", emp_conv.name, ignore_permissions=True, force=True)


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


def run_tests():
    import unittest
    frappe.in_test = True
    frappe.flags.in_test = True
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestConnectorDispatch,
        TestConnectorFlags,
        TestConnectorViews,
        TestConnectorNotification,
        TestConnectorOffset,
        TestConnectorPollerLock,
        TestConnectorRulesFromSite,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    print(f"RESULT: wasSuccessful={res.wasSuccessful()}, testsRun={res.testsRun}, errors={len(res.errors)}, failures={len(res.failures)}")
    if not res.wasSuccessful():
        raise SystemExit(1)
    return res.wasSuccessful()
