# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

import json
import re
import time
import requests
import frappe
from frappe.utils import now_datetime
from aios_v1.lib.llm_client import chat_stream
from aios_v1.lib.order_service import (
    get_active_catalog_prompt,
    get_active_draft_prompt,
    create_erpnext_sales_order,
    finalize_sales_order,
    cancel_sales_order_draft
)


TELEGRAM_API_BASE = "https://api.telegram.org"

def _sanitize_error(err: Exception | str, token: str = "") -> str:
    """
    Menyensor bot token dari pesan error agar tidak bocor ke log atau layar terminal.
    """
    msg = str(err)
    if token and token in msg:
        msg = msg.replace(token, "[REDACTED]")
    return msg



def get_telegram_setting() -> dict:
    """
    Mengambil konfigurasi bot Telegram dari DocType Single 'AIOS Telegram Setting'.
    """
    try:
        doc = frappe.get_single("AIOS Telegram Setting")
        token = doc.get_password("bot_token") or ""
        return {
            "bot_token": token,
            "bot_username": doc.bot_username or "aios_client_support_bot",
            "is_active": bool(doc.is_active),
            "lead_source": doc.lead_source or "Telegram",
        }
    except Exception as e:
        frappe.log_error(f"Gagal mengambil AIOS Telegram Setting: {str(e)}", "Telegram Service")
        return {
            "bot_token": "",
            "bot_username": "aios_client_support_bot",
            "is_active": False,
            "lead_source": "Telegram",
        }


def save_telegram_token(bot_token: str) -> bool:
    """
    Menyimpan token bot Telegram ke dalam DocType Single 'AIOS Telegram Setting'.
    """
    try:
        doc = frappe.get_single("AIOS Telegram Setting")
        doc.bot_token = bot_token
        doc.is_active = 1
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return True
    except Exception as e:
        frappe.log_error(f"Gagal menyimpan token Telegram: {str(e)}", "Telegram Service")
        return False


def test_telegram_connection() -> dict:
    """
    Menguji koneksi ke Telegram Bot API menggunakan getMe.
    """
    config = get_telegram_setting()
    token = config.get("bot_token")

    if not token:
        return {
            "success": False,
            "message": "Token bot belum diatur di AIOS Telegram Setting."
        }

    url = f"{TELEGRAM_API_BASE}/bot{token}/getMe"
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
        if data.get("ok"):
            return {
                "success": True,
                "bot": data.get("result", {}),
                "message": "Koneksi ke bot Telegram berhasil terhubung."
            }
        else:
            return {
                "success": False,
                "message": f"Telegram API error: {data.get('description', 'Unknown error')}"
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Gagal menghubungi server Telegram: {_sanitize_error(e, token)}"
        }


def send_telegram_message(
    chat_id: str | int,
    text: str,
    parse_mode: str = None,
    reply_markup: dict = None
) -> bool:
    """
    Mengirim pesan teks ke chat Telegram tertentu via Telegram Bot API,
    dengan dukungan tombol interaktif (reply_markup / inline keyboard).
    """
    config = get_telegram_setting()
    token = config.get("bot_token")

    if not token:
        frappe.log_error("Pengiriman pesan dibatalkan: bot token kosong.", "Telegram Service")
        return False

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        res = requests.post(url, json=payload, timeout=15)
        data = res.json()

        if data.get("ok"):
            return True

        # Jika gagal karena format Markdown, coba kirim ulang sebagai plain text
        if parse_mode and not data.get("ok"):
            payload.pop("parse_mode", None)
            retry_res = requests.post(url, json=payload, timeout=15)
            return retry_res.json().get("ok", False)

        return False
    except Exception as e:
        frappe.log_error(f"Error mengirim pesan Telegram ke {chat_id}: {_sanitize_error(e, token)}", "Telegram Service")
        return False


def answer_callback_query(callback_query_id: str, text: str = "") -> bool:
    """
    Menjawab callback_query dari tombol Inline Keyboard Telegram
    agar spinner loading pada tombol segera berhenti.
    """
    config = get_telegram_setting()
    token = config.get("bot_token")
    if not token or not callback_query_id:
        return False

    url = f"{TELEGRAM_API_BASE}/bot{token}/answerCallbackQuery"
    payload = {"callback_query_id": str(callback_query_id)}
    if text:
        payload["text"] = text

    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.json().get("ok", False)
    except Exception as e:
        frappe.log_error(f"Error menjawab callback query {callback_query_id}: {str(e)}", "Telegram Service")
        return False


def send_chat_action(chat_id: str | int, action: str = "typing") -> bool:
    """
    Mengirimkan aksi chat (seperti 'typing') ke Telegram agar pengguna melihat status 'sedang mengetik...'.
    """
    config = get_telegram_setting()
    token = config.get("bot_token")

    if not token:
        return False

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendChatAction"
    payload = {
        "chat_id": chat_id,
        "action": action
    }

    try:
        res = requests.post(url, json=payload, timeout=8)
        return res.json().get("ok", False)
    except Exception:
        return False


def get_or_create_session(chat_id: str | int, user_info: dict, last_message_text: str = "") -> str:
    """
    Mencari atau membuat sesi interaksi customer di DocType 'AIOS Telegram Session'.
    Mengembalikan nama record (ID sesi).
    """
    chat_id_str = str(chat_id)
    existing = frappe.get_all(
        "AIOS Telegram Session",
        filters={"chat_id": chat_id_str},
        fields=["name", "first_name", "username"],
        limit=1
    )

    now = now_datetime()

    if existing:
        session_name = existing[0]["name"]
        frappe.db.set_value(
            "AIOS Telegram Session",
            session_name,
            {
                "last_interaction": now,
                "last_message": last_message_text[:140] if last_message_text else "",
                "status": "Active"
            },
            update_modified=True
        )
        return session_name

    doc = frappe.new_doc("AIOS Telegram Session")
    doc.chat_id = chat_id_str
    doc.username = user_info.get("username") or ""
    doc.first_name = user_info.get("first_name") or ""
    doc.last_name = user_info.get("last_name") or ""
    doc.status = "Active"
    doc.last_interaction = now
    doc.last_message = last_message_text[:140] if last_message_text else ""
    doc.insert(ignore_permissions=True)

    return doc.name


def ensure_telegram_utm_source():
    """
    Memastikan nilai 'Telegram' tersedia di DocType 'UTM Source' ERPNext.
    """
    if frappe.db.exists("DocType", "UTM Source"):
        if not frappe.db.exists("UTM Source", "Telegram"):
            try:
                u = frappe.new_doc("UTM Source")
                u.name = "Telegram"
                u.utm_source = "Telegram"
                u.insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                pass


def create_or_link_erpnext_lead(session_name: str | int, user_info: dict, initial_message: str = "") -> str | None:
    """
    Menghubungkan atau membuat record Lead baru di modul CRM ERPNext
    berdasarkan data calon customer Telegram.
    Mengembalikan ID Lead yang tertaut (misal: 'CRM-LEAD-2026-00001').
    """
    try:
        # 1. Pastikan DocType Lead dari ERPNext tersedia
        if not frappe.db.exists("DocType", "Lead"):
            return None

        session_doc = frappe.get_doc("AIOS Telegram Session", session_name)
        if session_doc.lead:
            return session_doc.lead

        # 2. Pastikan UTM Source 'Telegram' terdaftar
        ensure_telegram_utm_source()

        first_name = (user_info.get("first_name") or user_info.get("username") or "Telegram Customer").strip()
        last_name = (user_info.get("last_name") or "").strip()
        lead_name = f"{first_name} {last_name}".strip()

        # 3. Buat record Lead baru di ERPNext
        lead_doc = frappe.new_doc("Lead")
        lead_doc.first_name = first_name
        lead_doc.last_name = last_name
        lead_doc.lead_name = lead_name
        lead_doc.status = "Lead"
        lead_doc.type = "Client"
        lead_doc.utm_source = "Telegram"

        lead_doc.insert(ignore_permissions=True)

        # 4. Tautkan Lead ke sesi Telegram
        session_doc.lead = lead_doc.name
        session_doc.save(ignore_permissions=True)
        frappe.db.commit()

        return lead_doc.name

    except Exception as e:
        frappe.log_error(f"Gagal menyinkronkan Lead ERPNext: {str(e)}", "Telegram Service")
        return None


def sync_all_pending_leads() -> int:
    """
    Menyinkronkan semua sesi Telegram yang belum tertaut ke record Lead di ERPNext.
    Berguna untuk backfill sesi lama.
    """
    sessions = frappe.get_all(
        "AIOS Telegram Session",
        filters={"lead": ("in", ["", None])},
        fields=["name", "chat_id", "first_name", "last_name", "username", "last_message"],
        limit_page_length=0,
    )

    count = 0
    for s in sessions:
        user_info = {
            "first_name": s.first_name,
            "last_name": s.last_name,
            "username": s.username
        }
        lead_name = create_or_link_erpnext_lead(s.name, user_info, s.last_message)
        if lead_name:
            count += 1

    return count



def get_recent_messages(session_name: str, limit: int = 10) -> list:
    """
    Mengambil riwayat percakapan terkini untuk konteks LLM.
    """
    msgs = frappe.get_all(
        "AIOS Telegram Message",
        filters={"session": session_name},
        fields=["sender", "message"],
        order_by="sent_at desc",
        limit_page_length=limit
    )

    # Balikkan urutan agar kronologis dari yang terlama ke terbaru
    msgs.reverse()

    history = []
    for m in msgs:
        role = "assistant" if m.sender == "bot" else "user"
        history.append({
            "role": role,
            "content": m.message or ""
        })

    return history


def generate_bot_reply(session_name: str, incoming_text: str, user_name: str = "") -> str:
    """
    Menghasilkan balasan AI yang cerdas, sopan, dan solutif menggunakan AIOS LLM.
    """
    name_greeting = f" Pelanggan bernama {user_name}." if user_name else ""

    # Ambil konfigurasi persona dan instruksi khusus dari AIOS Telegram Setting
    tone_instruction = "Gaya komunikasi: Ramah, santai, bersahabat, hangat, dan gunakan emotikon yang wajar dan menyenangkan."
    custom_instruction_text = ""
    try:
        setting = frappe.get_single("AIOS Telegram Setting")
        persona_tone = getattr(setting, "persona_tone", None) or "Ramah & Kasual"
        custom_instructions = getattr(setting, "custom_instructions", None) or ""

        if persona_tone == "Formal & Profesional":
            tone_instruction = (
                "Gaya komunikasi: Formal, baku, profesional, dan sopan seperti perwakilan korporat atau konsultan terpercaya. "
                "Gunakan tata bahasa yang baik dan hindari emotikon berlebihan."
            )
        elif persona_tone == "Ringkas & Solutif":
            tone_instruction = (
                "Gaya komunikasi: Sangat ringkas, padat, langsung ke inti solusi (to the point), efektif, dan efisien. "
                "Hindari basa-basi yang panjang."
            )
        else:
            tone_instruction = (
                "Gaya komunikasi: Ramah, santai, bersahabat, hangat, dan gunakan emotikon yang wajar dan menyenangkan."
            )

        if custom_instructions.strip():
            custom_instruction_text = f"\n\nInstruksi Khusus Tambahan dari Manajemen Klien:\n{custom_instructions.strip()}"
    except Exception as err:
        frappe.log_error(f"Gagal membaca setting persona chatbot: {str(err)}", "Telegram Service")

    # Ambil katalog produk aktif dan data pesanan aktif untuk panduan LLM
    catalog_prompt = get_active_catalog_prompt()
    active_draft_prompt = get_active_draft_prompt(session_name)
    draft_context_text = f"\n\n{active_draft_prompt}" if active_draft_prompt else ""

    order_detection_instruction = (
        f"\n\n{catalog_prompt}"
        f"{draft_context_text}\n\n"
        "Panduan Khusus Pemesanan Produk:\n"
        "- Jika pelanggan bertanya tentang ketersediaan atau harga barang, jawab berdasarkan katalog produk di atas.\n"
        "- Jika pelanggan secara eksplisit menyatakan ingin membeli atau memesan barang (contoh: 'saya mau pesan 2 T-shirt' atau 'beli 1 Laptop dong'), "
        "konfirmasikan pesanan tersebut dengan ramah, dan SERTAKAN tag tersembunyi persis di baris paling akhir balasan Anda dengan format JSON:\n"
        "<!--ORDER: [{\"item_code\": \"KODE_BARANG\", \"qty\": JUMLAH}]-->\n"
        "- Jika sebelumnya pelanggan sudah memesan dan kemudian MENAMBAHKAN produk lagi (contoh: 'sama 1 Laptop ya' atau 'tambah 2 pcs Buku'), "
        "konfirmasikan penambahan tersebut dengan ramah, dan keluarkan tag <!--ORDER: [...]--> HANYA untuk barang tambahannya saja.\n"
        "- CATATAN PANDUAN PENUTUP: Setiap kali Anda mengonfirmasi pesanan barang atau menjawab rincian total belanja, "
        "Anda WAJIB menyertakan kalimat penutup yang ramah di baris akhir balasan Anda yang mengarahkan pelanggan untuk mengetik kata 'selesai' jika sudah tidak ada tambahan: "
        "(contoh: 'Ketik \"selesai\" jika pesanan Anda sudah cukup, atau beri tahu kami jika masih ada yang ingin ditambahkan ya! 😊').\n"
        "- Jika pelanggan bertanya tentang total pesanan (contoh: 'totalnya berapa?', 'rekap dong', 'jadi berapa?'), "
        "jawablah rincian total secara ramah berdasarkan data pesanan aktif di atas, lalu sertakan catatan panduan agar pelanggan mengetik 'selesai' jika sudah cukup. "
        "JANGAN keluarkan tag <!--ORDER_CHECKOUT: true--> saat pelanggan hanya menanyakan total.\n"
        "- HANYA JIKA pelanggan secara EKSPLISIT menyatakan sudah selesai belanja (contoh: 'selesai', 'udah selesai', 'cukup', 'udah itu aja', 'g ad'), "
        "konfirmasikan ringkasan seluruh pesanan dan total harganya, tanyakan persetujuan pelanggan, dan SERTAKAN tag konfirmasi tersembunyi di baris paling akhir balasan Anda dengan format:\n"
        "<!--ORDER_CHECKOUT: true-->\n"
        "- Format tag wajib valid di dalam komentar HTML tersebut.\n"
        "- PENTING: Hanya keluarkan tag tersebut jika pelanggan BENAR-BENAR bermaksud membeli/memesan atau menyelesaikan pesanan. "
        "Jangan keluarkan tag jika pelanggan hanya sekadar bertanya info harga, spesifikasi, atau menyapa biasa."
    )

    system_prompt = (
        "Anda adalah AIOS Client Assistant, asisten virtual customer support resmi untuk perusahaan klien di platform AIOS."
        f"{name_greeting}\n\n"
        f"Panduan Nada Bicara:\n- {tone_instruction}\n\n"
        "Tugas utama Anda:\n"
        "- Menyapa pelanggan dengan sopan dalam bahasa Indonesia.\n"
        "- Menjawab pertanyaan seputar produk, layanan, atau konsultasi bisnis secara jelas dan membantu.\n"
        "- Jika pelanggan baru pertama kali menyapa atau bertanya, berikan sambutan hangat dan tanyakan apa yang bisa dibantu.\n"
        "- Hindari jawaban yang terlalu panjang atau bertele-tele agar nyaman dibaca di layar chat Telegram."
        f"{custom_instruction_text}"
        f"{order_detection_instruction}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    recent_history = get_recent_messages(session_name, limit=10)
    messages.extend(recent_history)

    # Cegah duplikasi jika incoming_text sudah sempat tersimpan di database sebelum fungsi ini dipanggil
    if not recent_history or recent_history[-1].get("content") != incoming_text or recent_history[-1].get("role") != "user":
        messages.append({"role": "user", "content": incoming_text})

    reply_text = ""
    for attempt in range(2):
        try:
            reply_chunks = []
            for chunk in chat_stream(messages, max_tokens=1500, timeout=35):
                reply_chunks.append(chunk)

            reply_text = "".join(reply_chunks).strip()
            if reply_text:
                break
            time.sleep(0.5)
        except Exception as e:
            frappe.log_error(f"Gagal memanggil LLM untuk Telegram reply (percobaan {attempt + 1}): {str(e)}", "Telegram Service")
            time.sleep(0.5)

    if not reply_text:
        reply_text = "Maaf, koneksi asisten sedang memuat respons. Boleh tolong ulangi pesan Anda?"

    return reply_text


def process_incoming_message(chat_id: str | int, user_info: dict, message_text: str) -> dict:
    """
    Alur utama pemrosesan pesan masuk Telegram:
    1. Kirim status 'typing...' ke Telegram seketika
    2. Amankan/buat sesi di AIOS Telegram Session
    3. Simpan pesan pelanggan ke AIOS Telegram Message (sender='user')
    4. Generate balasan AI
    5. Kirim balasan ke Telegram
    6. Simpan pesan balasan ke AIOS Telegram Message (sender='bot')
    """
    if not message_text:
        return {"success": False, "reason": "Pesan kosong"}

    sender_name = user_info.get("first_name") or user_info.get("username") or str(chat_id)
    now_str = time.strftime("%H:%M:%S")

    print(f"\n[{now_str}] 📩 Pesan masuk dari {sender_name} (Chat ID: {chat_id}):")
    print(f"  └── \"{message_text}\"")

    # 1. Kirim status 'typing...' ke Telegram agar di HP pengguna muncul 'sedang mengetik...'
    send_chat_action(chat_id, "typing")
    print(f"[{time.strftime('%H:%M:%S')}] 💬 Mengirim status 'sedang mengetik...' ke Telegram")

    # 2. Sesi & simpan pesan user ke database (langsung di-commit agar aman dari interupsi)
    session_name = get_or_create_session(chat_id, user_info, last_message_text=message_text)

    user_msg = frappe.new_doc("AIOS Telegram Message")
    user_msg.session = session_name
    user_msg.chat_id = str(chat_id)
    user_msg.sender = "user"
    user_msg.message = message_text
    user_msg.sent_at = now_datetime()
    user_msg.insert(ignore_permissions=True)
    frappe.db.commit()

    # 3. Generate balasan AI
    t_start = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] 🤖 Memanggil LLM AIOS untuk menyusun balasan...")
    display_name = user_info.get("first_name") or user_info.get("username") or ""
    raw_bot_reply = generate_bot_reply(session_name, message_text, user_name=display_name)
    duration = round(time.time() - t_start, 2)

    # 4. Deteksi tag pesanan <!--ORDER: [...]-->
    clean_reply = raw_bot_reply
    order_data = None

    order_match = re.search(r"<!--ORDER:\s*(\[.*?\])\s*-->", raw_bot_reply, re.DOTALL)
    if order_match:
        tag_json_str = order_match.group(1).strip()
        # Bersihkan tag dari teks balasan agar pelanggan tidak melihat kode teknis
        clean_reply = re.sub(r"<!--ORDER:\s*\[.*?\]\s*-->", "", raw_bot_reply, flags=re.DOTALL).strip()

        try:
            order_items = json.loads(tag_json_str)
            if isinstance(order_items, list) and order_items:
                order_result = create_erpnext_sales_order(session_name, order_items)
                if order_result.get("success"):
                    so_id = order_result["sales_order"]
                    grand_total = order_result.get("grand_total") or 0.0
                    is_update = order_result.get("is_update", False)
                    order_data = order_result
                    if is_update:
                        print(
                            f"[{time.strftime('%H:%M:%S')}] ➕ Item ditambahkan ke Draf Sales Order dari {sender_name}! "
                            f"Order: {so_id} (Total akumulasi baru: Rp {grand_total:,.0f})"
                        )
                    else:
                        print(
                            f"[{time.strftime('%H:%M:%S')}] 🛒 Pesanan baru terdeteksi dari {sender_name}! "
                            f"Draf Sales Order dibuat: {so_id} (Rp {grand_total:,.0f})"
                        )
                else:
                    err_msg = order_result.get("error", "Gagal memproses pesanan")
                    print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Gagal memproses Sales Order ERPNext: {err_msg}")
        except json.JSONDecodeError as json_err:
            print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Format JSON pesanan tidak valid: {str(json_err)}")

    # 4b. Deteksi tag konfirmasi checkout <!--ORDER_CHECKOUT...-->
    reply_markup = None
    checkout_match = re.search(r"<!--ORDER_CHECKOUT.*?-->", clean_reply, re.DOTALL)
    active_so = None

    if checkout_match:
        clean_reply = re.sub(r"<!--ORDER_CHECKOUT.*?-->", "", clean_reply, flags=re.DOTALL).strip()
        if order_data and order_data.get("sales_order"):
            active_so = order_data["sales_order"]
        elif frappe.db.exists("AIOS Telegram Session", session_name):
            active_so = frappe.db.get_value("AIOS Telegram Session", session_name, "sales_order")

        if active_so and frappe.db.get_value("Sales Order", active_so, "docstatus") == 0:
            # Tombol interaktif tanpa emoji sesuai instruksi user
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "Setujui Pesanan", "callback_data": f"order_approve:{active_so}"},
                        {"text": "Batalkan Pesanan", "callback_data": f"order_cancel:{active_so}"}
                    ]
                ]
            }
            print(f"[{time.strftime('%H:%M:%S')}] 📋 Permintaan konfirmasi pesanan dikirim ke {sender_name} (Order: {active_so})")

    # 5. Kirim balasan bersih ke Telegram (disertai tombol jika checkout)
    send_success = send_telegram_message(chat_id, clean_reply, reply_markup=reply_markup)

    # 6. Simpan balasan bot ke database
    bot_msg = frappe.new_doc("AIOS Telegram Message")
    bot_msg.session = session_name
    bot_msg.chat_id = str(chat_id)
    bot_msg.sender = "bot"
    bot_msg.message = clean_reply
    bot_msg.sent_at = now_datetime()
    if order_data and order_data.get("sales_order"):
        bot_msg.sales_order = order_data["sales_order"]
    elif checkout_match and active_so:
        bot_msg.sales_order = active_so
    bot_msg.insert(ignore_permissions=True)
    frappe.db.commit()

    snippet = clean_reply[:75] + ("..." if len(clean_reply) > 75 else "")
    print(f"[{time.strftime('%H:%M:%S')}] ✅ Balasan terkirim ke Telegram ({duration}s):")
    print(f"  └── \"{snippet}\"\n")

    return {
        "success": True,
        "session": session_name,
        "reply": clean_reply,
        "order": order_data,
        "sent_to_telegram": send_success
    }


def process_callback_query(callback_query: dict) -> dict:
    """
    Menangani aksi tombol interaktif (Inline Keyboard) dari pelanggan Telegram.
    Aksi:
    - order_approve:<so_id> -> Menyetujui dan memfinalkan Sales Order
    - order_cancel:<so_id> -> Membatalkan draf Sales Order
    """
    query_id = callback_query.get("id")
    data = callback_query.get("data") or ""
    from_user = callback_query.get("from", {})
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id") or from_user.get("id")
    sender_name = from_user.get("first_name") or from_user.get("username") or "Customer"

    # 1. Hentikan spinner loading pada tombol Telegram
    answer_callback_query(query_id)

    session_name = frappe.db.get_value("AIOS Telegram Session", {"chat_id": str(chat_id)}, "name")
    if not session_name:
        return {"success": False, "error": "Sesi tidak ditemukan"}

    if data.startswith("order_approve:"):
        so_id = data.split(":", 1)[1].strip()
        print(f"[{time.strftime('%H:%M:%S')}] ✅ Pesanan DISETUJUI oleh {sender_name}! Order: {so_id}")

        result = finalize_sales_order(session_name, so_id)
        reply_text = (
            f"Terima kasih, {sender_name}! Pesanan Anda ({so_id}) telah resmi disetujui "
            f"dan dicatat ke sistem kami. Tim kami akan segera memprosesnya! 🙏"
        )
        send_telegram_message(chat_id, reply_text)

        # Catat balasan bot ke database
        bot_msg = frappe.new_doc("AIOS Telegram Message")
        bot_msg.session = session_name
        bot_msg.chat_id = str(chat_id)
        bot_msg.sender = "bot"
        bot_msg.message = reply_text
        bot_msg.sent_at = now_datetime()
        bot_msg.sales_order = so_id
        bot_msg.insert(ignore_permissions=True)
        frappe.db.commit()

        return {"success": True, "action": "approve", "sales_order": so_id}

    elif data.startswith("order_cancel:"):
        so_id = data.split(":", 1)[1].strip()
        print(f"[{time.strftime('%H:%M:%S')}] ❌ Pesanan DIBATALKAN oleh {sender_name}! Order: {so_id}")

        result = cancel_sales_order_draft(session_name, so_id)
        reply_text = (
            f"Pesanan Anda ({so_id}) telah dibatalkan. "
            f"Jika ada produk lain yang ingin dipesan, silakan chat kami kembali ya. 😊"
        )
        send_telegram_message(chat_id, reply_text)

        # Catat balasan bot ke database
        bot_msg = frappe.new_doc("AIOS Telegram Message")
        bot_msg.session = session_name
        bot_msg.chat_id = str(chat_id)
        bot_msg.sender = "bot"
        bot_msg.message = reply_text
        bot_msg.sent_at = now_datetime()
        bot_msg.insert(ignore_permissions=True)
        frappe.db.commit()

        return {"success": True, "action": "cancel", "sales_order": so_id}

    return {"success": False, "error": "Aksi tidak dikenal"}


def poll_telegram_updates(limit: int = 10, timeout: int = 5, single_run: bool = True) -> int:
    """
    Mengambil pesan baru dari Telegram menggunakan metode Long-Polling (getUpdates).
    Mendukung single_run=True (sekali periksa) atau single_run=False (loop terus menerus).
    Menggunakan requests.Session() persistent untuk koneksi stabil.
    """
    config = get_telegram_setting()
    token = config.get("bot_token")

    if not token or not config.get("is_active"):
        print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Bot Telegram belum aktif atau token kosong.")
        return 0

    cache_key = "aios_telegram_last_update_id"
    last_update_id = frappe.cache.get_value(cache_key) or 0

    processed_count = 0
    session = requests.Session()

    try:
        while True:
            offset = last_update_id + 1 if last_update_id else 0
            url = f"{TELEGRAM_API_BASE}/bot{token}/getUpdates"
            params = {
                "offset": offset,
                "limit": limit,
                "timeout": timeout
            }

            try:
                res = session.get(url, params=params, timeout=timeout + 10)
                data = res.json()

                if not data.get("ok"):
                    err_desc = data.get("description", "Unknown error")
                    err_code = data.get("error_code")
                    print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Telegram API error ({err_code}): {err_desc}")
                    if single_run:
                        break
                    time.sleep(3)
                    continue

                updates = data.get("result", [])
                if not updates:
                    if single_run:
                        break
                    time.sleep(1)
                    continue

                for u in updates:
                    update_id = u.get("update_id")

                    callback_query = u.get("callback_query")
                    if callback_query:
                        process_callback_query(callback_query)
                        processed_count += 1
                        if update_id and update_id > last_update_id:
                            last_update_id = update_id
                            frappe.cache.set_value(cache_key, last_update_id)
                        continue

                    message = u.get("message")
                    if not message:
                        if update_id and update_id > last_update_id:
                            last_update_id = update_id
                            frappe.cache.set_value(cache_key, last_update_id)
                        continue

                    text = message.get("text")
                    if not text:
                        if update_id and update_id > last_update_id:
                            last_update_id = update_id
                            frappe.cache.set_value(cache_key, last_update_id)
                        continue

                    chat = message.get("chat", {})
                    chat_id = chat.get("id")
                    from_user = message.get("from", {})

                    process_incoming_message(chat_id, from_user, text)
                    processed_count += 1

                    if update_id and update_id > last_update_id:
                        last_update_id = update_id
                        frappe.cache.set_value(cache_key, last_update_id)

                if single_run:
                    break

            except requests.exceptions.Timeout:
                # Long polling timeout wajar jika tidak ada pesan masuk dalam jeda waktu tersebut
                if single_run:
                    break
                continue

            except Exception as e:
                safe_err = _sanitize_error(e, token)
                frappe.log_error(f"Error saat polling Telegram: {safe_err}", "Telegram Service")
                print(f"[{time.strftime('%H:%M:%S')}] ❌ Error saat polling: {safe_err}")
                if single_run:
                    break
                time.sleep(3)

    finally:
        session.close()

    return processed_count


def start_polling():
    """
    Menjalankan loop polling bot Telegram secara terus-menerus.
    Dapat dipanggil via:
    bench --site aios.localhost execute aios_v1.lib.telegram_service.start_polling
    """
    status = test_telegram_connection()
    if not status.get("success"):
        print(f"[{time.strftime('%H:%M:%S')}] ❌ [Telegram Bot] Gagal memulai: {status.get('message')}")
        return

    bot_info = status.get("bot", {})
    print(f"\n========================================================")
    print(f" 🤖 AIOS Telegram Bot Service (Live Listener)")
    print(f" Bot Username : @{bot_info.get('username')}")
    print(f" Bot Name     : {bot_info.get('first_name')}")
    print(f" Status       : AKTIF & MENDENGARKAN PESAN...")
    print(f"========================================================")
    print("Tekan Ctrl+C kapan saja untuk menghentikan polling.\n")

    try:
        poll_telegram_updates(limit=10, timeout=5, single_run=False)
    except KeyboardInterrupt:
        print(f"\n[{time.strftime('%H:%M:%S')}] 🛑 Polling dihentikan oleh pengguna.")

