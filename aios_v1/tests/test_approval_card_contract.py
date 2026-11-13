"""Static UI contract tests for Ekasa Desk ApprovalCardWindow.vue."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APPROVAL_CARD = (
    REPO_ROOT / "frontend" / "src" / "components" / "windows" / "ApprovalCardWindow.vue"
)
FORMAT_UTILS = REPO_ROOT / "frontend" / "src" / "utils" / "format.ts"


def _read_approval_card() -> str:
    return APPROVAL_CARD.read_text(encoding="utf-8")


def _extract_block(source: str, tag: str) -> str:
    match = re.search(rf"<{tag}[^>]*>(.*)</{tag}>", source, re.DOTALL)
    assert match is not None, f"Missing <{tag}> block in {APPROVAL_CARD.name}"
    return match.group(1)


class TestApprovalCardContract(unittest.TestCase):
    """Enforce readable draft formatting and expiry gating in ApprovalCardWindow.vue."""

    def test_customer_info_and_proposed_data_use_labeled_ui_without_raw_json(self) -> None:
        text = _read_approval_card()
        script = _extract_block(text, "script")
        template = _extract_block(text, "template")
        format_src = FORMAT_UTILS.read_text(encoding="utf-8")

        # Required formatters must exist in utils/format.ts and be imported
        for fn_name in ("formatCurrency", "formatDateTime", "formatNumber", "formatShortDate"):
            self.assertIn(f"export function {fn_name}", format_src)
            self.assertIn(fn_name, script)

        # Raw prettyJson must no longer be rendered for customer_info or unconditional data
        self.assertNotIn("prettyJson(payload.customer_info)", text)
        self.assertNotIn("prettyJson(payload?.data", text)

        # Technical diff sections ("Sebelum" and "Sesudah") stay untouched
        self.assertIn("prettyJson(payload.before)", template)
        self.assertIn("prettyJson(payload.after)", template)

        # Customer info Indonesian labels and Individual/Company mapping
        for expected in (
            "Data Pelanggan Baru",
            "Customer",
            "Tipe",
            "No. HP",
            "Alamat",
            "Contact Person",
            "Perorangan",
            "Perusahaan",
        ):
            self.assertIn(expected, text)
        self.assertRegex(script, r"(?i)\bindividual\b")
        self.assertRegex(script, r"(?i)\bcompany\b")

        # Proposed data table headers, summary labels, and Rupiah ('IDR') formatting
        for expected in (
            "Data diusulkan",
            "No.",
            "Nama Item",
            "Jumlah",
            "Harga Satuan",
            "Subtotal",
            "Total",
            "Tanggal Pengiriman",
            "Metode Pembayaran",
            "'IDR'",
        ):
            self.assertIn(expected, text)

        # Payment method lookup must cover both data and customer_info (guest SO drafts)
        self.assertIn("mode_of_payment", script)
        self.assertIn("payment_method", script)
        self.assertIn("<table", template)

        # Empty string filter and zero-safe numeric helper
        self.assertIn("toFiniteNumber", script)
        self.assertIn("cleanText", script)

    def test_expired_draft_hides_actions_and_shows_expiry_notice(self) -> None:
        text = _read_approval_card()
        script = _extract_block(text, "script")
        template = _extract_block(text, "template")

        # Script defines isExpired checking terminal status EXPIRED vs PENDING_APPROVAL + expiry
        self.assertIn("const isExpired = computed(", script)
        self.assertIn("'EXPIRED'", script)
        self.assertIn("isPastExpiry", script)
        self.assertIn("onUnmounted", script)

        # approve() and reject() must guard against expiry via shared blockIfExpired helper
        self.assertIn("function blockIfExpired()", script)
        guard_match = re.search(
            r"function blockIfExpired\(\).*?^\}", script, re.DOTALL | re.MULTILINE
        )
        approve_match = re.search(
            r"async function approve\(\).*?^\}", script, re.DOTALL | re.MULTILINE
        )
        reject_match = re.search(
            r"async function reject\(\).*?^\}", script, re.DOTALL | re.MULTILINE
        )
        self.assertIsNotNone(guard_match)
        self.assertIsNotNone(approve_match)
        self.assertIsNotNone(reject_match)
        assert guard_match is not None and approve_match is not None and reject_match is not None
        self.assertIn("Draf sudah kedaluwarsa.", script)
        self.assertIn("isDraftExpiredNow", guard_match.group(0))
        self.assertIn("EXPIRED_NOTICE", guard_match.group(0))
        self.assertIn("if (blockIfExpired()) return;", approve_match.group(0))
        self.assertIn("if (blockIfExpired()) return;", reject_match.group(0))

        # Template order: active pending actions -> expired notice -> processed fallback
        actions_branch = 'v-if="isPending && !isExpired"'
        expired_branch = 'v-else-if="isExpired"'
        processed_branch = 'v-else class="ac-note"'

        self.assertIn(actions_branch, template)
        self.assertIn(expired_branch, template)
        self.assertIn(processed_branch, template)
        self.assertIn("Draf sudah kedaluwarsa.", template)

        pos_actions = template.index(actions_branch)
        pos_expired = template.index(expired_branch)
        pos_processed = template.index(processed_branch)
        self.assertLess(pos_actions, pos_expired)
        self.assertLess(pos_expired, pos_processed)

        # "Draft sudah diproses" stays strictly inside the non-pending, non-expired else branch
        pos_processed_text = template.index("Draft sudah diproses")
        self.assertGreater(pos_processed_text, pos_processed)

    def test_active_pending_and_executed_cash_payment_preserved(self) -> None:
        template = _extract_block(_read_approval_card(), "template")

        for expected in (
            "Tolak",
            "Setujui & Eksekusi",
            "Konfirmasi Penolakan",
            "isExecutedSalesOrder && !paymentEntryName",
            "Sudah Bayar (Cash)",
            "Payment Entry:",
        ):
            self.assertIn(expected, template)
