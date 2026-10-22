"""Sanitasi error dan pencatatan terpusat untuk AIOS.

Aturan:
- Tidak ada error yang ditelan; handler wajib memanggil ``log_exception`` atau ``raise``.
- Pesan log disanitasi: token, password, API key, path, nama site/DB tidak ditulis mentah.
- Response ke frontend memakai ``safe_error``; tidak pernah memuat ``str(exc)`` atau traceback.
"""

import re

import frappe

REDACTED = "[REDACTED]"

_PATTERNS = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), REDACTED),
    (re.compile(r"bot\d+:[A-Za-z0-9_\-]{20,}"), REDACTED),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1" + REDACTED),
    (
        re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;'\"]+"),
        r"\1" + REDACTED,
    ),
    (re.compile(r"/home/[^\s:'\"]+"), "[PATH]"),
    (re.compile(r"/sites/[^\s:'\"]+"), "[PATH]"),
    (re.compile(r"\b_[a-f0-9]{16}\b"), "[DB]"),
)


def _conf_value(key):
    conf = getattr(frappe, "conf", None)
    if conf is None or not hasattr(conf, "get"):
        return ""
    return str(conf.get(key) or "")


def _known_secrets():
    values = (
        _conf_value("db_password"),
        _conf_value("db_root_password"),
        _conf_value("root_password"),
        _conf_value("encryption_key"),
    )
    # Jangan mask nilai pendek seperti "admin": bisa merusak kata lain di log.
    return [value for value in values if value and len(value) >= 8]


def sanitize_text(value) -> str:
    """Bersihkan teks dari kredensial dan identitas infrastruktur."""
    text = str(value or "")
    for secret in _known_secrets():
        text = text.replace(secret, REDACTED)

    site = getattr(getattr(frappe, "local", None), "site", None)
    if site:
        text = text.replace(str(site), "[SITE]")

    for key in ("db_name", "db_user"):
        value = _conf_value(key)
        if value:
            text = text.replace(value, "[DB]")

    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def log_exception(title: str, exc: BaseException | None = None, context: str | None = None) -> None:
    """Catat kegagalan ke Error Log Frappe dengan pesan tersanitasi."""
    parts = []
    if context:
        parts.append(str(context))
    if exc is not None:
        parts.append(f"{type(exc).__name__}: {exc}")
    trace = frappe.get_traceback() if exc is not None else ""
    if trace:
        parts.append(trace)

    frappe.log_error(
        title=sanitize_text(title)[:140],
        message=sanitize_text("\n".join(part for part in parts if part)),
    )


def safe_error(message: str = "Terjadi kesalahan internal.", code: str = "INTERNAL_ERROR") -> dict:
    """Payload error yang aman untuk frontend; tidak memuat detail internal."""
    return {"success": False, "error": message, "code": code}
