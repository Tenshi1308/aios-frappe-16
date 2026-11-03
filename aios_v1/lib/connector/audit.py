"""Deterministic conversation audit for the Telegram channel.

Everything here is arithmetic over `AIOS Message` timestamps and regex over
message content. No LLM: these numbers are shown to a PIC/Owner as facts, so
they must be reproducible and testable.
"""

from __future__ import annotations

import re

import frappe

from aios_v1.lib.connector import rules as connector_rules
from aios_v1.lib.error_utils import log_exception

MESSAGE_DOCTYPE = "AIOS Message"
# A customer message left without an agent reply for longer than this is
# reported as unanswered. Configurable per site; never a literal at call sites.
DEFAULT_UNANSWERED_MINUTES = 60
DEFAULT_RESPONSE_TARGET_SECONDS = 300


def _conversation_messages(conversation: str) -> list[dict]:
    return frappe.get_all(
        MESSAGE_DOCTYPE,
        filters={"conversation": conversation},
        fields=["name", "role", "content", "creation"],
        order_by="creation asc",
        limit_page_length=0,
    )


def response_metrics(messages: list[dict], target_seconds: int = DEFAULT_RESPONSE_TARGET_SECONDS) -> dict:
    """Average first-reply latency and how many replies missed the target."""
    pending_at = None
    latencies: list[float] = []
    for message in messages:
        if message.get("role") == "user":
            if pending_at is None:
                pending_at = message.get("creation")
        elif pending_at is not None:
            try:
                latencies.append((message["creation"] - pending_at).total_seconds())
            except (TypeError, AttributeError) as exc:
                log_exception("AIOS Connector Audit Timestamps", exc=exc)
            pending_at = None

    if not latencies:
        return {
            "samples": 0,
            "average_seconds": None,
            "over_target": 0,
            "target_seconds": target_seconds,
        }
    return {
        "samples": len(latencies),
        "average_seconds": round(sum(latencies) / len(latencies), 1),
        "over_target": sum(1 for value in latencies if value > target_seconds),
        "target_seconds": target_seconds,
    }


def unanswered(messages: list[dict], now=None) -> dict:
    """True when the last message is from the customer and is still waiting."""
    from frappe.utils import now_datetime

    if not messages:
        return {"waiting": False, "minutes": None}
    last = messages[-1]
    if last.get("role") != "user":
        return {"waiting": False, "minutes": None}
    reference = now or now_datetime()
    try:
        minutes = round((reference - last["creation"]).total_seconds() / 60, 1)
    except (TypeError, AttributeError) as exc:
        log_exception("AIOS Connector Audit Unanswered", exc=exc)
        return {"waiting": False, "minutes": None}
    return {"waiting": True, "minutes": minutes}


def sop_checklist(messages: list[dict], checklist: list[dict] | None = None) -> list[dict]:
    """Evaluate each checklist item against the agent replies.

    A check passes when at least one agent message matches one of its patterns.
    Items without patterns are reported as not-evaluable instead of silently
    passing — a reviewer must never read a false "compliant".
    """
    checklist = checklist if checklist is not None else connector_rules.load_config().get("sop_checklist") or []
    items = checklist or list(connector_rules.DEFAULT_SOP_CHECKLIST)
    agent_text = "\n".join(
        message.get("content") or "" for message in messages if message.get("role") != "user"
    )
    results = []
    for item in items:
        patterns = item.get("patterns") or ()
        if not patterns:
            results.append({"key": item.get("key"), "label": item.get("label"), "passed": None})
            continue
        passed = False
        for pattern in patterns:
            try:
                if re.search(pattern, agent_text, re.IGNORECASE):
                    passed = True
                    break
            except re.error as exc:
                log_exception("AIOS Connector SOP Pattern", exc=exc, context=str(item.get("key")))
        results.append({"key": item.get("key"), "label": item.get("label"), "passed": passed})
    return results


def summarize(conversation: str, config: dict | None = None) -> dict:
    """One audit snapshot for a conversation. Read-only."""
    config = config or connector_rules.load_config()
    messages = _conversation_messages(conversation)
    checklist = sop_checklist(messages, config.get("sop_checklist") or None)
    evaluated = [item for item in checklist if item["passed"] is not None]
    passed = [item for item in evaluated if item["passed"]]
    return {
        "messages": len(messages),
        "response": response_metrics(
            messages,
            int(config.get("response_target_seconds") or DEFAULT_RESPONSE_TARGET_SECONDS),
        ),
        "unanswered": unanswered(messages),
        "sop": checklist,
        "sop_percent": round(100 * len(passed) / len(evaluated)) if evaluated else None,
        "unanswered_minutes_threshold": int(
            config.get("unanswered_minutes") or DEFAULT_UNANSWERED_MINUTES
        ),
    }
