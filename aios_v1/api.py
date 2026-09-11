import frappe
import requests
import json
import re
from typing import Optional

def safe_parse_json(raw_text: str) -> dict:
    """
    Parser JSON tahan-banting: membersihkan trailer SSE seperti 'data: [DONE]'
    atau teks tambahan yang ditempelkan gateway AI.
    """
    text = raw_text.strip()
    if "data: [DONE]" in text:
        text = text.split("data: [DONE]")[0].strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            clean_json = text[start:end+1]
            return json.loads(clean_json)
        raise

@frappe.whitelist(allow_guest=True)
def ask_intelligence(message: Optional[str] = None, context: Optional[str] = None) -> dict:
    """
    Endpoint utama Department Intelligence AIOS.
    Menggunakan Type Annotation sesuai standar Frappe versi terbaru.
    """
    if not message:
        # Fallback reading from frappe.form_dict if passed as form-data
        message = frappe.form_dict.get("message")
        
    if not message:
        return {
            "success": False,
            "error": "Pesan tidak boleh kosong."
        }

    # 1. Ambil konfigurasi dari DocType AIOS Setting
    try:
        settings = frappe.get_single("AIOS Setting")
        api_key = settings.get_password("api_key")
    except Exception as e:
        api_key = None
        settings = None

    if not api_key:
        return {
            "success": False,
            "error": "API Key belum diatur di AIOS Setting! Silakan isi terlebih dahulu di Desk."
        }

    base_url = (settings.base_url or "").strip() if settings else ""
    model_name = (settings.model_name or "").strip() if settings else ""
    temperature = settings.temperature if (settings and settings.temperature is not None) else 0.2

    if not base_url:
        return {
            "success": False,
            "error": "Base URL belum diatur di AIOS Setting! Silakan isi terlebih dahulu di Desk."
        }

    if not model_name:
        return {
            "success": False,
            "error": "Model Name belum diatur di AIOS Setting! Silakan isi terlebih dahulu di Desk."
        }
    system_ethos = (settings.system_ethos or (
        "Kamu adalah Department Intelligence AI untuk sistem ERP perusahaan.\n"
        "1. Anti-halusinasi: Jangan mengarang data jika tidak tersedia.\n"
        "2. Sebutkan sumber data dengan objektif.\n"
        "3. Gunakan Bahasa Indonesia yang profesional dan jelas.\n"
        "4. Berikan rekomendasi keputusan bisnis yang konkret."
    )) if settings else ""

    # 2. Susun Payload Chat
    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        f"{system_ethos}\n\n"
        f"Konteks Tambahan Perusahaan:\n{context if context else 'Belum ada konteks data terlampir.'}"
    )

    payload = {
        "model": model_name,
        "temperature": float(temperature),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
    }

    # 3. Panggil LLM API
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        data = safe_parse_json(response.text)
        
        reply = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return {
            "success": True,
            "reply": reply,
            "usage": usage,
            "model": model_name
        }

    except Exception as e:
        frappe.log_error(title="AIOS Intelligence Call Error", message=str(e))
        return {
            "success": False,
            "error": f"Gagal menghubungi AI Engine: {str(e)}"
        }
