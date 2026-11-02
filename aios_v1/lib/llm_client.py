import json
import time
from urllib.parse import urlparse

import requests
import frappe
from aios_v1.lib.error_utils import log_exception

def get_llm_config():
    setting = frappe.get_single("AIOS Setting")
    meta = frappe.get_meta("AIOS Setting")
    base_url = (setting.base_url or "").strip()
    api_key = (setting.get_password("api_key", raise_exception=False) or "").strip()
    model = (setting.model_name or "").strip()

    if setting.temperature is not None:
        temperature = float(setting.temperature)
    else:
        temperature = float(meta.get_field("temperature").default)

    meta_max_tokens = int(meta.get_field("default_max_tokens").default)
    raw_max_tokens = setting.get("default_max_tokens")
    if raw_max_tokens:
        try:
            default_max_tokens = int(raw_max_tokens)
        except (TypeError, ValueError) as exc:
            log_exception("AIOS LLM Setting Max Tokens", exc=exc)
            default_max_tokens = meta_max_tokens
    else:
        default_max_tokens = meta_max_tokens

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
        "default_max_tokens": default_max_tokens,
        "timeout": 90.0,
    }


def chat_stream(messages, max_tokens=None, temperature=None, timeout=None, usage=None, tools=None, tool_calls=None):
    """Stream content delta and aggregate fragmented tool calls into `tool_calls`."""
    cfg = get_llm_config()
    meta = frappe.get_meta("AIOS Setting")
    meta_default_tokens = int(meta.get_field("default_max_tokens").default)
    token_limit = (
        max_tokens
        if max_tokens is not None
        else (cfg.get("default_max_tokens") or meta_default_tokens)
    )
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
        "max_tokens": token_limit,
        "temperature": temperature if temperature is not None else cfg["temperature"],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        payload["tools"] = tools

    max_attempts = 2

    for attempt in range(1, max_attempts + 1):
        collected_calls = {}
        finish_reason = ""
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
                except Exception as exc:
                    log_exception("AIOS LLM Stream Chunk", exc=exc)
                    continue
                if usage is not None and chunk.get("usage"):
                    usage.update(chunk["usage"])
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                if choices[0].get("finish_reason"):
                    finish_reason = choices[0]["finish_reason"]
                delta_obj = choices[0].get("delta") or {}
                delta = delta_obj.get("content", "")
                if delta:
                    yield delta
                for fragment in delta_obj.get("tool_calls") or []:
                    index = fragment.get("index", 0)
                    call = collected_calls.setdefault(
                        index,
                        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                    )
                    if fragment.get("id") and not call["id"]:
                        call["id"] = fragment["id"]
                    function = fragment.get("function") or {}
                    if function.get("name") and not call["function"]["name"]:
                        call["function"]["name"] = function["name"]
                    if function.get("arguments"):
                        call["function"]["arguments"] += function["arguments"]

            if finish_reason and usage is not None:
                usage["finish_reason"] = finish_reason
            if tool_calls is not None:
                tool_calls.extend(collected_calls[index] for index in sorted(collected_calls))

            return

        except Exception as exc:
            log_exception("AIOS LLM Request", exc=exc)
            if attempt < max_attempts:
                time.sleep(1)
                continue

    if usage is not None:
        usage["failed"] = True
    yield "Mohon maaf, server AI memerlukan waktu lebih lama dari biasanya. Silakan coba ajukan pertanyaan kembali."


def chat_completion(messages, max_tokens=None, temperature=None, timeout=None) -> str:
    """One-shot non-streaming completion untuk tugas internal seperti compaction/summarization."""
    cfg = get_llm_config()
    meta = frappe.get_meta("AIOS Setting")
    meta_default_tokens = int(meta.get_field("default_max_tokens").default)
    token_limit = (
        max_tokens
        if max_tokens is not None
        else (cfg.get("default_max_tokens") or meta_default_tokens)
    )
    req_timeout = timeout if timeout is not None else cfg["timeout"]
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": token_limit,
        "temperature": temperature if temperature is not None else cfg["temperature"],
        "stream": False,
    }
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=req_timeout)
            if not res.ok:
                raise Exception(f"HTTP {res.status_code}: {res.text[:200]}")
            data = res.json()
            choices = data.get("choices") or []
            if not choices:
                return ""
            msg = choices[0].get("message") or {}
            return msg.get("content") or ""
        except Exception as exc:
            log_exception("AIOS LLM Completion Request", exc=exc)
            if attempt < max_attempts:
                time.sleep(1)
                continue
    return ""
