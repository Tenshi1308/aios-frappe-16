import json
import time
from urllib.parse import urlparse

import requests
import frappe

def get_llm_config():
    setting = frappe.get_single("AIOS Setting")
    base_url = (setting.base_url or "").strip()
    api_key = (setting.get_password("api_key", raise_exception=False) or "").strip()
    model = (setting.model_name or "").strip()
    temperature = float(setting.temperature) if setting.temperature is not None else 0.3

    if not api_key:
        frappe.throw("API Key belum diisi di AIOS Setting pada Frappe Desk.")
    if not base_url:
        frappe.throw("Base URL belum diisi di AIOS Setting pada Frappe Desk.")
    if not model:
        frappe.throw("Model Name belum diisi di AIOS Setting pada Frappe Desk.")

    return {
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
        "model": model,
        "temperature": temperature,
        "timeout": 90.0
    }

def chat_stream(messages, max_tokens=2048, temperature=None, timeout=None, usage=None):
    """Stream teks delta; `usage` (dict) diisi token & metadata dari provider."""
    cfg = get_llm_config()
    if usage is not None:
        usage["provider"] = urlparse(cfg["base_url"]).netloc or ""
        usage["model"] = cfg["model"]
    req_timeout = timeout if timeout is not None else cfg["timeout"]
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}"
    }
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature if temperature is not None else cfg["temperature"],
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    max_attempts = 2

    for attempt in range(1, max_attempts + 1):
        try:
            res = requests.post(url, headers=headers, json=payload, stream=True, timeout=req_timeout)
            if not res.ok:
                raise Exception(f"HTTP {res.status_code}: {res.text[:200]}")

            res.encoding = "utf-8"

            for line in res.iter_lines(decode_unicode=True):
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "AIOS LLM Stream Chunk")
                    continue
                if usage is not None and chunk.get("usage"):
                    usage.update(chunk["usage"])
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {}).get("content", "")
                if delta:
                    yield delta

            return

        except Exception:
            frappe.log_error(frappe.get_traceback(), "AIOS LLM Request")
            if attempt < max_attempts:
                time.sleep(1)
                continue

    if usage is not None:
        usage["failed"] = True
    yield "Mohon maaf, server AI memerlukan waktu lebih lama dari biasanya. Silakan coba ajukan pertanyaan kembali."
