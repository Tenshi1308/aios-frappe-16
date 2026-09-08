# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

import json
import time
import requests
import frappe
from frappe.utils import now_datetime
from aios_v1.lib.llm_client import chat_stream


TELEGRAM_API_BASE = "https://api.telegram.org"


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
            "message": f"Gagal menghubungi server Telegram: {str(e)}"
        }


def send_telegram_message(chat_id: str | int, text: str, parse_mode: str = None) -> bool:
    """
    Mengirim pesan teks ke chat Telegram tertentu via Telegram Bot API.
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
        frappe.log_error(f"Error mengirim pesan Telegram ke {chat_id}: {str(e)}", "Telegram Service")
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
        fields=["name", "chat_id", "first_name", "last_name", "username", "last_message"]
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



def get_recent_messages(session_name: str, limit: int = 6) -> list:
    """
    Mengambil riwayat percakapan terkini untuk konteks LLM.
    """
    msgs = frappe.get_all(
        "AIOS Telegram Message",
        filters={"session": session_name},
        fields=["sender", "message"],
        order_by="sent_at asc",
        limit_page_length=limit
    )

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
    )

    messages = [{"role": "system", "content": system_prompt}]
    recent_history = get_recent_messages(session_name, limit=4)
    messages.extend(recent_history)
    messages.append({"role": "user", "content": incoming_text})

    try:
        reply_chunks = []
        for chunk in chat_stream(messages, max_tokens=600, timeout=25):
            reply_chunks.append(chunk)

        reply_text = "".join(reply_chunks).strip()
        if not reply_text:
            reply_text = "Halo! Terima kasih telah menghubungi kami. Ada yang bisa kami bantu hari ini?"

        return reply_text

    except Exception as e:
        frappe.log_error(f"Gagal memanggil LLM untuk Telegram reply: {str(e)}", "Telegram Service")
        return "Halo! Terima kasih telah menghubungi kami. Saat ini asisten kami sedang memproses permintaan Anda, ada yang bisa kami bantu?"


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
    bot_reply = generate_bot_reply(session_name, message_text, user_name=display_name)
    duration = round(time.time() - t_start, 2)

    # 4. Kirim balasan ke Telegram
    send_success = send_telegram_message(chat_id, bot_reply)

    # 5. Simpan balasan bot ke database
    bot_msg = frappe.new_doc("AIOS Telegram Message")
    bot_msg.session = session_name
    bot_msg.chat_id = str(chat_id)
    bot_msg.sender = "bot"
    bot_msg.message = bot_reply
    bot_msg.sent_at = now_datetime()
    bot_msg.insert(ignore_permissions=True)
    frappe.db.commit()

    snippet = bot_reply[:75] + ("..." if len(bot_reply) > 75 else "")
    print(f"[{time.strftime('%H:%M:%S')}] ✅ Balasan terkirim ke Telegram ({duration}s):")
    print(f"  └── \"{snippet}\"\n")

    return {
        "success": True,
        "session": session_name,
        "reply": bot_reply,
        "sent_to_telegram": send_success
    }


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
                frappe.log_error(f"Error saat polling Telegram: {str(e)}", "Telegram Service")
                print(f"[{time.strftime('%H:%M:%S')}] ❌ Error saat polling: {str(e)}")
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

