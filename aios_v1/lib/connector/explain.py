"""LLM explanation for an already-raised flag.

The model is never asked to decide fraud. It receives the deterministic signal
and a redacted transcript slice, and returns a short justification for the
reviewer. Output is stored as `reason_text`; it never becomes a verdict.
"""

from __future__ import annotations

import frappe

from aios_v1.lib.connector.redact import redact
from aios_v1.lib.error_utils import log_exception
from aios_v1.lib.llm_client import chat_completion

MAX_TRANSCRIPT_MESSAGES = 8
MAX_REASON_CHARS = 400

SYSTEM_PROMPT = (
    "Anda membantu tim audit internal. Sebuah aturan otomatis sudah menandai "
    "percakapan ini. Tugas Anda HANYA menjelaskan alasan singkat mengapa "
    "percakapan tersebut cocok dengan tanda yang sudah ditetapkan.\n"
    "Aturan wajib:\n"
    "- Jangan menilai atau menyimpulkan bahwa seseorang melakukan kecurangan.\n"
    "- Jangan menuduh individu.\n"
    "- Jangan menambah fakta yang tidak ada di potongan percakapan.\n"
    "- Tulis 1-2 kalimat Bahasa Indonesia yang netral untuk reviewer manusia."
)


def explain_flag(flag_label: str, excerpt: str, transcript: list[dict]) -> str:
    """Return a short neutral explanation, or "" when the model is unavailable.

    Failures are logged and swallowed: an explanation is a convenience for the
    reviewer, never a gate. The flag itself already exists without it.
    """
    lines = []
    for message in (transcript or [])[-MAX_TRANSCRIPT_MESSAGES:]:
        sender = message.get("sender") or message.get("role") or "?"
        content = message.get("content") or message.get("message") or ""
        if content:
            lines.append(f"{sender}: {redact(content)}")
    if not lines:
        return ""

    user_prompt = (
        f"Tanda yang terdeteksi: {flag_label}\n"
        f"Kutipan pemicu: {redact(excerpt)}\n\n"
        "Potongan percakapan (data pribadi sudah disamarkan):\n"
        + "\n".join(lines)
        + "\n\nTulis alasan singkat untuk reviewer."
    )
    try:
        answer = chat_completion(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=200,
            temperature=0.2,
            timeout=30,
        )
    except Exception as exc:
        log_exception("AIOS Connector Flag Explanation", exc=exc)
        return ""
    return (answer or "").strip()[:MAX_REASON_CHARS]


def spend_hint() -> str:
    """Kept for parity with other lib modules; no cost estimate is computed here."""
    return ""
