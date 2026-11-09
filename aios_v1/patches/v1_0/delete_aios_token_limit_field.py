"""Hapus Custom Field User.aios_token_limit (#5).

Latar belakang: sejak #7b kuota token PoC hanya satu gerbang site —
`AIOS Setting.site_token_limit` vs `site_tokens_used`. `User.aios_token_limit`
bukan gerbang, tidak pernah ditulis lagi, dan seluruh nilainya 0 di kedua site.
`User.aios_tokens_used` tetap dipakai sebagai statistik harian.

Definisi field sudah dihapus dari `USER_CUSTOM_FIELDS` (setup.py), jadi
`after_migrate` tidak akan membuatnya ulang. Patch ini membuang dokumen
Custom Field yang masih tertinggal di site lama memakai helper resmi Frappe
(`delete_custom_fields`), yang menjalankan `CustomField.on_trash`: membersihkan
Property Setter, DocType Layout, dan cache. Kolom database tidak ikut terhapus
oleh migrate — pembersihannya lewat trim per-doctype `User`.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields

from aios_v1.lib.error_utils import log_exception

DOCTYPE = "User"
FIELDNAME = "aios_token_limit"


def execute():
    if not frappe.db.exists("Custom Field", {"dt": DOCTYPE, "fieldname": FIELDNAME}):
        return

    try:
        delete_custom_fields({DOCTYPE: [FIELDNAME]})
    except Exception as exc:
        log_exception("AIOS Patch Delete aios_token_limit", exc=exc, context=FIELDNAME)
        raise

    frappe.db.commit()
