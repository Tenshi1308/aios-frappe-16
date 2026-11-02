"""Unit & Integration tests untuk Context Compactor & Memory Buffer (AIOS V1)."""

import json
from unittest.mock import patch

import frappe
try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore

from aios_v1.lib.context_manager import (
    DEFAULT_CONTEXT_WINDOW_LIMIT,
    DEFAULT_COMPACT_THRESHOLD_PERCENT,
    KEEP_VERBATIM_COUNT,
    build_conversation_context,
    calculate_conversation_context_stats,
    estimate_tokens,
    get_context_window_settings,
    prune_intra_turn_tool_results,
    summarize_messages,
)


class TestConversationCompactor(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.db.set_single_value("AIOS Setting", "context_window_limit", DEFAULT_CONTEXT_WINDOW_LIMIT)
        frappe.db.set_single_value("AIOS Setting", "compact_threshold_percent", DEFAULT_COMPACT_THRESHOLD_PERCENT)
        frappe.clear_document_cache("AIOS Setting", "AIOS Setting")

        self.test_user = "test_compactor@example.com"
        if not frappe.db.exists("User", self.test_user):
            user = frappe.new_doc("User")
            user.email = self.test_user
            user.first_name = "Test"
            user.last_name = "Compactor"
            user.insert(ignore_permissions=True)

        self.conv = frappe.new_doc("AIOS Conversation")
        self.conv.user = self.test_user
        self.conv.branch = "sales"
        self.conv.title = "Test Compaction Sesi"
        self.conv.insert(ignore_permissions=True)

    def tearDown(self):
        try:
            setting = frappe.get_single("AIOS Setting")
            setting.context_window_limit = self._orig_context_window_limit
            setting.compact_threshold_percent = self._orig_compact_threshold_percent
            setting.save(ignore_permissions=True)
            frappe.clear_document_cache("AIOS Setting", "AIOS Setting")
        except Exception:
            pass
        frappe.db.rollback()
        super().tearDown()

    def _add_message(self, role: str, content: str, worker_key: str = "manager") -> str:
        msg = frappe.new_doc("AIOS Message")
        msg.conversation = self.conv.name
        msg.role = role
        msg.worker_key = worker_key
        msg.content = content
        msg.insert(ignore_permissions=True)
        return msg.name

    def test_context_window_settings_defaults_and_override(self):
        frappe.db.set_single_value("AIOS Setting", "context_window_limit", DEFAULT_CONTEXT_WINDOW_LIMIT)
        frappe.db.set_single_value("AIOS Setting", "compact_threshold_percent", DEFAULT_COMPACT_THRESHOLD_PERCENT)
        frappe.clear_document_cache("AIOS Setting", "AIOS Setting")

        limit, thresh = get_context_window_settings()
        self.assertGreaterEqual(limit, 1000)
        self.assertTrue(20 <= thresh <= 95)

        # Uji override via setting
        setting = frappe.get_single("AIOS Setting")
        setting.context_window_limit = 200000
        setting.compact_threshold_percent = 80
        setting.save(ignore_permissions=True)
        frappe.clear_document_cache("AIOS Setting", "AIOS Setting")

        limit2, thresh2 = get_context_window_settings()
        self.assertEqual(limit2, 200000)
        self.assertEqual(thresh2, 80)

    def test_short_conversation_retains_all_messages_verbatim(self):
        self._add_message("user", "Halo sales")
        self._add_message("manager", "Halo, ada yang bisa dibantu?")
        self._add_message("user", "Saya ingin pesan laptop")

        history = build_conversation_context(
            conversation_id=self.conv.name,
            new_user_message="Saya ingin pesan laptop",
        )
        # 2 pesan riwayat (pesan ketiga adalah new_user_message yang disisihkan)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["content"], "Halo sales")
        self.assertEqual(history[1]["content"], "Halo, ada yang bisa dibantu?")

        # Pastikan belum ada ringkasan
        conv_doc = frappe.get_doc("AIOS Conversation", self.conv.name)
        self.assertFalse(bool(conv_doc.session_summary))
        self.assertEqual(conv_doc.compacted_message_count, 0)

    def test_compaction_triggered_when_threshold_exceeded(self):
        # Buat 8 pesan riwayat
        for i in range(8):
            role = "user" if i % 2 == 0 else "manager"
            self._add_message(role, f"Pesan nomor {i}: transaksi dan negosiasi produk LAP-ENT-14")

        fake_summary = "Pelanggan telah menegosiasikan LAP-ENT-14 dan menyepakati harga."

        # Mock settings agar batas token kecil sehingga compaction terpicu tanpa mengotori DB
        with patch("aios_v1.lib.context_manager.get_context_window_settings", return_value=(50, 50)):
            with patch("aios_v1.lib.context_manager.chat_completion", return_value=fake_summary):
                history = build_conversation_context(
                    conversation_id=self.conv.name,
                    new_user_message="Lanjutkan ke tahap Quotation",
                )

        # 1 ringkasan sistem + 4 pesan terakhir verbatim
        self.assertEqual(len(history), 1 + KEEP_VERBATIM_COUNT)
        self.assertEqual(history[0]["role"], "system")
        self.assertIn("RINGKASAN STATUS TRANSAKSI SESI SEBELUMNYA", history[0]["content"])
        self.assertIn(fake_summary, history[0]["content"])

        # 4 pesan terakhir verbatim
        for item in history[1:]:
            self.assertIn("Pesan nomor", item["content"])

        # Verifikasi database terupdate secara atomik
        conv_doc = frappe.get_doc("AIOS Conversation", self.conv.name)
        self.assertEqual(conv_doc.session_summary, fake_summary)
        self.assertEqual(conv_doc.compacted_message_count, 4)

        # Pesan mentah di database tetap utuh 8 pesan (tidak dihapus)
        raw_count = frappe.db.count("AIOS Message", {"conversation": self.conv.name})
        self.assertEqual(raw_count, 8)

    def test_subsequent_turn_reuses_summary(self):
        # Simulasi percakapan yang sudah memiliki ringkasan
        self.conv.session_summary = "Ringkasan lama dari turn sebelumnya."
        self.conv.compacted_message_count = 4
        self.conv.save(ignore_permissions=True)

        # Tambahkan 6 pesan total (4 lama + 2 baru)
        for i in range(6):
            role = "user" if i % 2 == 0 else "manager"
            self._add_message(role, f"Pesan ke-{i}")

        history = build_conversation_context(
            conversation_id=self.conv.name,
            new_user_message="Pesan ke-5",
        )

        self.assertEqual(history[0]["role"], "system")
        self.assertIn("Ringkasan lama dari turn sebelumnya.", history[0]["content"])

    def test_prune_intra_turn_tool_results_when_above_limit(self):
        large_json = json.dumps({"status": "success", "doctype": "Sales Order", "rows": [{"item": "X"}] * 500})
        messages = [
            {"role": "user", "content": "Cek Sales Order"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": large_json},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c2"}]},
            {"role": "tool", "tool_call_id": "c2", "content": large_json},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c3"}]},
            {"role": "tool", "tool_call_id": "c3", "content": '{"status":"ok","name":"SO-1"}'},
        ]

        # Context limit kecil agar threshold 60% terlampaui
        pruned = prune_intra_turn_tool_results(messages, context_limit=500)
        # Tool pertama (c1) dipangkas
        tool_1 = next(m for m in pruned if m.get("tool_call_id") == "c1")
        self.assertIn("_pruned", tool_1["content"])
        self.assertIn("Sales Order", tool_1["content"])
        self.assertLess(len(tool_1["content"]), len(large_json))

        # Tool terbaru (c3) tetap utuh
        tool_3 = next(m for m in pruned if m.get("tool_call_id") == "c3")
        self.assertEqual(tool_3["content"], '{"status":"ok","name":"SO-1"}')

    def test_summarize_messages_fallback_on_llm_error(self):
        messages = [
            {"role": "user", "content": "Toko Berkah beli 2 unit LAP-ENT-14"},
            {"role": "manager", "content": "Quotation SAL-QTN-2026-00002 terbit"},
        ]
        with patch("aios_v1.lib.context_manager.chat_completion", side_effect=Exception("LLM Network Timeout")):
            fallback = summarize_messages("Ringkasan awal.", messages)

        self.assertIn("Ringkasan awal.", fallback)
        self.assertIn("Toko Berkah beli 2 unit", fallback)

    def test_calculate_conversation_context_stats(self):
        self._add_message("user", "Pesan pertama pelanggan")
        self._add_message("manager", "Pesan balasan manajer sales")

        stats = calculate_conversation_context_stats(
            conversation_id=self.conv.name,
            branch="sales",
            system_tokens=1500,
            tool_tokens=2500,
        )

        self.assertGreater(stats["total"], 4000)
        self.assertEqual(stats["system"], 1500)
        self.assertEqual(stats["tools"], 2500)
        self.assertGreater(stats["messages"], 0)
        self.assertGreater(stats["limit"], 1000)
        self.assertGreater(stats["percent"], 0.0)
        self.assertFalse(stats["compacted"])

        # Uji status compacted saat session_summary terisi
        self.conv.session_summary = "Ringkasan memori sesi aktif."
        self.conv.compacted_message_count = 2
        self.conv.save(ignore_permissions=True)

        stats2 = calculate_conversation_context_stats(
            conversation_id=self.conv.name,
            branch="sales",
            system_tokens=1000,
            tool_tokens=1000,
        )
        self.assertTrue(stats2["compacted"])

        # Uji resolusi otomatis tanpa passing manual (simulasi alur reload/refresh browser)
        stats_auto = calculate_conversation_context_stats(
            conversation_id=self.conv.name,
            branch="sales",
        )
        self.assertGreater(stats_auto["tools"], 2000)
        self.assertGreater(stats_auto["system"], 1000)
        self.assertGreater(stats_auto["total"], 3000)
