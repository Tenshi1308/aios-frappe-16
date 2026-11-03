"""Deterministic risk rules for the Telegram channel.

Hard signals only — regex and thresholds, no LLM. The model never decides
whether something is fraud; it may only explain a flag that these rules already
raised (see `explain.py`).

Catalog is product content (same pattern as `plugin_manager/registry.py`), so a
site can override thresholds and phrases through
`AIOS Telegram Setting.connector_config_json` without a code change.
"""

from __future__ import annotations

import json
import re

import frappe

from aios_v1.lib.error_utils import log_exception

SETTING_DOCTYPE = "AIOS Telegram Setting"
CONFIG_FIELD = "connector_config_json"

# Discount above this percentage needs owner approval; anything higher is a
# signal that a rep promised terms they cannot grant.
DEFAULT_DISCOUNT_THRESHOLD = 20

DEFAULT_RULES = (
    {
        "key": "personal_account",
        "label": "Meminta transfer ke rekening pribadi",
        "severity": "high",
        "patterns": (
            r"rekening\s+pribadi",
            r"transfer\s+(?:ke|ker?)\s+rek(?:ening)?\s+(?:saya|aku|pribadi)",
            r"no\s*rek(?:ening)?\s+(?:saya|pribadi)",
            r"kirim\s+ke\s+rekening\s+(?:saya|pribadi)",
        ),
    },
    {
        "key": "off_authority_discount",
        "label": "Diskon di luar wewenang",
        "severity": "high",
        "patterns": (
            r"diskon\s+(\d{1,3})\s*(?:%|persen)",
            r"potong(?:an)?\s+(\d{1,3})\s*(?:%|persen)",
            r"harga\s+khusus\s+(\d{1,3})\s*(?:%|persen)",
        ),
        "threshold_key": "discount_threshold_percent",
    },
    {
        "key": "sop_tone",
        "label": "Nada tidak sesuai SOP layanan",
        "severity": "medium",
        "patterns": (
            r"sudah\s+(?:saya\s+)?jelaskan\s+berkali",
            r"kenapa\s+tidak\s+paham",
            r"baca\s+(?:dong|lagi)",
        ),
    },
    {
        "key": "forbidden_phrase",
        "label": "Frasa terlarang",
        "severity": "high",
        "patterns": (),
        "phrase_list_key": "forbidden_phrases",
    },
)

# Default SOP checklist used by the deterministic audit. `key` is stable and
# stored on the flag evidence; `label` is what the reviewer reads.
DEFAULT_SOP_CHECKLIST = (
    {"key": "greeting", "label": "Salam pembuka", "patterns": (r"\b(?:halo|hai|selamat\s+(?:pagi|siang|sore|malam)|kak)\b",)},
    {"key": "offer_help", "label": "Menawarkan bantuan", "patterns": (r"\b(?:bisa\s+(?:saya\s+)?bantu|ada\s+yang\s+bisa\s+(?:saya\s+)?bantu|dengan\s+senang)\b",)},
    {"key": "confirm_order", "label": "Konfirmasi pesanan", "patterns": (r"\b(?:konfirmasi|pesanan\s+anda|nomor\s+pesanan|sudah\s+kami\s+catat)\b",)},
)

DEFAULT_CONFIG = {
    "discount_threshold_percent": DEFAULT_DISCOUNT_THRESHOLD,
    "forbidden_phrases": [],
    "rules": [],
    "sop_checklist": [],
}


def load_config() -> dict:
    """Merge site override over the catalog defaults.

    An empty or invalid JSON value falls back to defaults and is logged; the
    connector must never silently run with a half-parsed policy.
    """
    config = dict(DEFAULT_CONFIG)
    try:
        raw = frappe.db.get_single_value(SETTING_DOCTYPE, CONFIG_FIELD)
    except Exception as exc:  # field may not be migrated yet
        log_exception("AIOS Connector Config Read", exc=exc)
        raw = None
    if not raw:
        return config
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Connector Config Parse", exc=exc)
        return config
    if not isinstance(parsed, dict):
        log_exception("AIOS Connector Config Shape", context="nilai bukan object JSON")
        return config
    for key, value in parsed.items():
        if key in config and value is not None:
            config[key] = value
    return config


def _compiled_rules(config: dict) -> list[dict]:
    """Build the active rule set: catalog defaults plus site overrides by key."""
    overrides = {
        rule.get("key"): rule
        for rule in config.get("rules") or []
        if isinstance(rule, dict) and rule.get("key")
    }
    active = []
    for base in DEFAULT_RULES:
        override = overrides.get(base["key"]) or {}
        merged = dict(base)
        if override.get("patterns"):
            merged["patterns"] = tuple(override["patterns"])
        if override.get("label"):
            merged["label"] = override["label"]
        if override.get("severity"):
            merged["severity"] = override["severity"]
        compiled = []
        for pattern in merged.get("patterns") or ():
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error as exc:
                log_exception("AIOS Connector Rule Pattern", exc=exc, context=merged["key"])
        merged["_compiled"] = compiled
        active.append(merged)
    return active


def _excerpt(text: str, match: re.Match) -> str:
    start = max(0, match.start() - 40)
    end = min(len(text), match.end() + 40)
    return text[start:end].strip()


def evaluate(text: str, config: dict | None = None) -> list[dict]:
    """Return every rule hit for one message. Empty list means no hard signal."""
    if not text:
        return []
    config = config or load_config()
    hits: list[dict] = []
    threshold = config.get("discount_threshold_percent") or DEFAULT_DISCOUNT_THRESHOLD
    forbidden = [phrase for phrase in (config.get("forbidden_phrases") or []) if phrase]

    for rule in _compiled_rules(config):
        for pattern in rule["_compiled"]:
            matched = None
            for match in pattern.finditer(text):
                if rule.get("threshold_key"):
                    groups = [group for group in match.groups() if group]
                    if groups and int(groups[0]) <= int(threshold):
                        continue
                matched = match
                break
            if matched is not None:
                hits.append(
                    {
                        "rule_key": rule["key"],
                        "label": rule["label"],
                        "severity": rule["severity"],
                        "excerpt": _excerpt(text, matched),
                    }
                )
                break  # one hit per rule is enough evidence

        list_key = rule.get("phrase_list_key")
        if list_key:
            lowered = text.lower()
            for phrase in forbidden:
                if phrase.lower() in lowered:
                    hits.append(
                        {
                            "rule_key": rule["key"],
                            "label": f"{rule['label']}: {phrase}",
                            "severity": rule["severity"],
                            "excerpt": phrase,
                        }
                    )

    return hits
