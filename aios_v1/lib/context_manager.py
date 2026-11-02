"""Pengelola Memori Sesi & Context Compactor Dinamis untuk AIOS V1.

Mengadopsi pola ConversationSummaryBufferMemory secara native:
- Menjaga daya ingat seluruh percakapan dalam sesi aktif.
- Mencegah ledakan token / context overflow saat percakapan panjang atau investigasi berulang.
- Menyimpan ringkasan sesi (session_summary) pada AIOS Conversation secara persisten.
- Mempertahankan pesan-pesan terbaru secara utuh (verbatim).
"""

import json
from typing import Any

import frappe
from aios_v1.lib.error_utils import log_exception
from aios_v1.lib.llm_client import chat_completion

DEFAULT_CONTEXT_WINDOW_LIMIT = 128000
DEFAULT_COMPACT_THRESHOLD_PERCENT = 75
KEEP_VERBATIM_COUNT = 4
MAX_PRUNED_TOOL_CHARS = 350


def estimate_tokens(text_or_obj: Any) -> int:
    """Estimasi jumlah token secara heuristik (~3.8 karakter per token)."""
    if text_or_obj is None:
        return 0
    if isinstance(text_or_obj, str):
        return max(1, int(len(text_or_obj) / 3.8)) if text_or_obj else 0
    if isinstance(text_or_obj, dict):
        content = str(text_or_obj.get("content") or "")
        tool_calls = json.dumps(text_or_obj.get("tool_calls") or [])
        return estimate_tokens(content) + estimate_tokens(tool_calls) + 4
    if isinstance(text_or_obj, (list, tuple)):
        return sum(estimate_tokens(item) for item in text_or_obj)
    return max(1, int(len(str(text_or_obj)) / 3.8))


def get_context_window_settings() -> tuple[int, int]:
    """Baca context_window_limit dan compact_threshold_percent dari AIOS Setting."""
    try:
        setting = frappe.get_single("AIOS Setting")
        meta = frappe.get_meta("AIOS Setting")

        limit_raw = setting.get("context_window_limit")
        if limit_raw:
            context_limit = max(10, int(limit_raw))
        else:
            meta_default = meta.get_field("context_window_limit")
            context_limit = int(meta_default.default) if meta_default and meta_default.default else DEFAULT_CONTEXT_WINDOW_LIMIT

        thresh_raw = setting.get("compact_threshold_percent")
        if thresh_raw:
            compact_threshold = max(20, min(95, int(thresh_raw)))
        else:
            meta_default = meta.get_field("compact_threshold_percent")
            compact_threshold = int(meta_default.default) if meta_default and meta_default.default else DEFAULT_COMPACT_THRESHOLD_PERCENT

        return context_limit, compact_threshold
    except Exception as exc:
        log_exception("AIOS Context Settings Read", exc=exc)
        return DEFAULT_CONTEXT_WINDOW_LIMIT, DEFAULT_COMPACT_THRESHOLD_PERCENT


def summarize_messages(existing_summary: str, messages_to_summarize: list[dict]) -> str:
    """Panggil model secara non-streaming untuk memperbarui ringkasan sesi bisnis."""
    if not messages_to_summarize:
        return existing_summary or ""

    system_prompt = (
        "Anda adalah asisten perangkum memori sesi bisnis untuk AIOS enterprise. "
        "Tugas Anda adalah memperbarui ringkasan sesi percakapan secara padat, faktual, dan terstruktur. "
        "CATAT HAL-HAL PENTING DENGAN JELAS:\n"
        "- Nama customer/partner, item barang/jasa, kuantitas, harga satuan, dan total nilai transaksi.\n"
        "- Dokumen ERPNext resmi yang telah dibuat/disetujui/ditolak (Quotation, Sales Order, Invoice, Payment, Delivery Note) beserta nomor resminya (mis. SAL-ORD-2026-00105).\n"
        "- Akun kas/bank, gudang (warehouse), dan metode pembayaran yang telah dipilih.\n"
        "- Kesepakatan penting, alasan penolakan draf jika ada, dan status siklus operasional saat ini.\n"
        "ATURAN: Tulis padat dalam bahasa Indonesia, tanpa salam pembuka atau basa-basi."
    )

    user_lines = []
    if existing_summary:
        user_lines.append(f"[RINGKASAN STATUS SEBELUMNYA]:\n{existing_summary.strip()}\n")
    user_lines.append("[PERCAKAPAN BARU YANG HARUS DIRANGKUM]:")
    for m in messages_to_summarize:
        role_label = "Pengguna" if m.get("role") == "user" else "AI"
        content = (m.get("content") or "").strip()
        if content:
            user_lines.append(f"- {role_label}: {content}")

    user_lines.append("\nPerbarui ringkasan sesi dengan menggabungkan poin-poin kunci di atas secara kronologis:")
    user_prompt = "\n".join(user_lines)

    try:
        summary_reply = chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1024,
            temperature=0.1,
            timeout=45.0,
        )
        cleaned = (summary_reply or "").strip()
        if cleaned:
            return cleaned
    except Exception as exc:
        log_exception("AIOS Conversation Summarizer", exc=exc)

    # Fallback aman bila LLM gagal merespons: pertahankan ringkasan lama + poin ringkas
    fallback_parts = []
    if existing_summary:
        fallback_parts.append(existing_summary)
    for m in messages_to_summarize[-4:]:
        snippet = (m.get("content") or "")[:120].strip()
        if snippet:
            fallback_parts.append(f"• {m.get('role')}: {snippet}...")
    return "\n".join(fallback_parts)


def build_conversation_context(
    conversation_id: str,
    worker_def: dict | None = None,
    new_user_message: str = "",
) -> list[dict]:
    """Susun riwayat pesan untuk LLM dengan auto-compactor bila mendekati batas konteks.
    
    1. Mengambil riwayat pesan sesi.
    2. Jika estimasi token melampaui ambang batas: rangkum pesan lama dan simpan ke AIOS Conversation.
    3. Kembalikan format llm_messages: [Summary Message (opsional)] + [Recent Verbatim Messages].
    """
    if not conversation_id or str(conversation_id).startswith("new:"):
        return []

    if not frappe.db.exists("AIOS Conversation", str(conversation_id)):
        return []

    try:
        conv_doc = frappe.get_doc("AIOS Conversation", str(conversation_id))
    except Exception as exc:
        log_exception("AIOS Context Conversation Read", exc=exc)
        return []

    all_messages = frappe.get_all(
        "AIOS Message",
        filters={"conversation": str(conversation_id)},
        fields=["name", "role", "worker_key", "content", "creation"],
        order_by="creation asc",
    )
    if not all_messages:
        return []

    # Sisihkan pesan pengguna saat ini yang baru saja disimpan agar riwayat tidak dobel
    if (
        all_messages
        and new_user_message
        and all_messages[-1].get("role") == "user"
        and (all_messages[-1].get("content") or "").strip() == new_user_message.strip()
    ):
        history_messages = all_messages[:-1]
    else:
        history_messages = all_messages

    if not history_messages:
        existing_summary = (conv_doc.session_summary or "").strip()
        if existing_summary:
            return [{
                "role": "system",
                "content": f"[RINGKASAN STATUS TRANSAKSI SESI SEBELUMNYA]:\n{existing_summary}",
            }]
        return []

    context_limit, compact_threshold = get_context_window_settings()
    threshold_tokens = int(context_limit * compact_threshold / 100)

    existing_summary = (conv_doc.session_summary or "").strip()
    compacted_count = int(conv_doc.compacted_message_count or 0)

    # Hitung estimasi token seluruh pesan riwayat yang belum terkompresi
    uncompacted_messages = (
        history_messages[compacted_count:]
        if compacted_count < len(history_messages)
        else history_messages[-KEEP_VERBATIM_COUNT:]
    )
    current_tokens = (
        estimate_tokens(existing_summary)
        + sum(estimate_tokens(m.get("content")) for m in uncompacted_messages)
        + estimate_tokens(new_user_message)
    )

    # Periksa apakah perlu compaction (hanya jika pesan melebihi batas simpan verbatim)
    if len(history_messages) > KEEP_VERBATIM_COUNT and current_tokens >= threshold_tokens:
        messages_to_summarize = history_messages[:-KEEP_VERBATIM_COUNT]
        verbatim_messages = history_messages[-KEEP_VERBATIM_COUNT:]

        new_summary = summarize_messages(existing_summary, messages_to_summarize)
        if new_summary:
            existing_summary = new_summary
            conv_doc.session_summary = new_summary
            conv_doc.compacted_message_count = len(messages_to_summarize)
            conv_doc.save(ignore_permissions=True)
            frappe.db.commit()
            active_messages = verbatim_messages
        else:
            active_messages = history_messages[-KEEP_VERBATIM_COUNT:]
    else:
        # Jika belum mencapai threshold, gunakan pesan yang belum terkompresi
        if existing_summary and compacted_count > 0:
            active_messages = history_messages[compacted_count:]
            if len(active_messages) < KEEP_VERBATIM_COUNT:
                active_messages = history_messages[-KEEP_VERBATIM_COUNT:]
        else:
            active_messages = history_messages

    # Susun payload llm_messages
    llm_history = []
    if existing_summary:
        llm_history.append({
            "role": "system",
            "content": f"[RINGKASAN STATUS TRANSAKSI SESI SEBELUMNYA]:\n{existing_summary}",
        })

    for m in active_messages:
        content = m.get("content") or ""
        if worker_def is None and m.get("worker_key") and m["worker_key"] != "manager":
            content = f"[{m['worker_key']}]: {content}"
        llm_history.append({
            "role": "user" if m.get("role") == "user" else "assistant",
            "content": content,
        })

    return llm_history


def prune_intra_turn_tool_results(llm_messages: list[dict], context_limit: int) -> list[dict]:
    """Pangkas output tool-tool lama dalam 1 turn bila ukuran token akumulasi mencapai 60% limit.
    
    Menjaga tool_call_id dan struktur peran 'tool' tetap valid agar provider LLM tidak menolak payload.
    """
    total_tokens = sum(estimate_tokens(msg) for msg in llm_messages)
    prune_threshold = int(context_limit * 0.60)
    if total_tokens < prune_threshold:
        return llm_messages

    # Cari pesan-pesan tool lama (sebelum 2 putaran tool terakhir)
    tool_indices = [idx for idx, msg in enumerate(llm_messages) if msg.get("role") == "tool"]
    if len(tool_indices) <= 2:
        return llm_messages

    indices_to_prune = tool_indices[:-2]
    pruned = False
    for idx in indices_to_prune:
        msg = llm_messages[idx]
        raw_content = str(msg.get("content") or "")
        if len(raw_content) > MAX_PRUNED_TOOL_CHARS:
            try:
                data = json.loads(raw_content)
                status = data.get("status") or "ok"
                doctype = data.get("doctype") or ""
                docname = data.get("name") or data.get("document") or ""
                summary_data = {
                    "status": status,
                    "doctype": doctype,
                    "document": docname,
                    "_pruned": "Detail data dipangkas otomatis untuk menghemat ruang konteks.",
                }
                msg["content"] = json.dumps(summary_data)
            except Exception as exc:
                log_exception("AIOS Context Tool Parse", exc=exc, context="Non-JSON tool output fallback to truncation")
                msg["content"] = raw_content[:MAX_PRUNED_TOOL_CHARS] + "... [dipangkas]"
            pruned = True

    if pruned:
        log_exception("AIOS Context Pruning", context=f"Output tool lama dipangkas. Total token sebelumnya: {total_tokens}")

    return llm_messages
