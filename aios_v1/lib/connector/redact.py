"""PII redaction for the fraud-explanation LLM call.

The transcript stored in `AIOS Message` stays raw: it is the audit evidence.
Only the payload handed to the model is redacted. This is deliberately narrow —
it is not a general anonymiser.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

# Ordered: email, then phone (an Indonesian mobile number is also a long digit
# run, so it must be claimed before the generic account pattern), then accounts.
_PATTERNS = (
    # Email addresses.
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    # Indonesian phone numbers.
    (re.compile(r"(?<!\d)(?:\+62|62|0)8\d{1,3}[-\s]?\d{3,4}[-\s]?\d{3,5}(?!\d)"), "[TELEPON]"),
    # Bank account numbers written in groups (10+ digits total).
    (re.compile(r"\b\d{2,4}(?:[-\s]?\d{4}){2,4}\b"), "[REKENING]"),
    # Bank account numbers written as one long digit run.
    (re.compile(r"\b\d{10,}\b"), "[REKENING]"),
)


def redact(text: str) -> str:
    """Return `text` with account numbers, phone numbers, and emails masked."""
    if not text:
        return ""
    cleaned = str(text)
    for pattern, replacement in _PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def redact_messages(messages: list[dict]) -> list[dict]:
    """Redact only the `content` of chat messages; keys and roles are untouched."""
    result = []
    for message in messages or []:
        if isinstance(message, dict):
            copy = dict(message)
            copy["content"] = redact(copy.get("content") or "")
            result.append(copy)
        else:
            result.append(message)
    return result
