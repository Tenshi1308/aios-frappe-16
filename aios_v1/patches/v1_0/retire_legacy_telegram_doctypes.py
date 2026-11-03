"""Retire the legacy Telegram channel DocTypes and drop their tables.

Background (report, F2): the old channel stored its own transcript in
`AIOS Telegram Session` / `AIOS Telegram Message`. Those DocTypes are retired in
favour of `AIOS Message` + `AIOS Channel Thread`, and their service modules are
deleted.

`bench migrate` only removes the `DocType` row (`frappe/model/sync.py:165-200`
— "Deleting the entry doesn't delete any data"), so the physical tables survive
and must be dropped here. The drop is guarded: if a table still holds rows, the
patch refuses and logs, because silently discarding channel history is not
recoverable. `AIOS Telegram Setting` is kept — it holds the bot credential.
"""

import frappe

from aios_v1.lib.error_utils import log_exception

RETIRED_DOCTYPES = ("AIOS Telegram Session", "AIOS Telegram Message")


def _table_for(doctype: str) -> str:
    return f"tab{doctype}"


def _has_rows(table: str) -> bool:
    try:
        return bool(frappe.db.sql(f"select 1 from `{table}` limit 1"))
    except Exception as exc:
        # Missing table is the expected end state on a fresh site.
        log_exception("AIOS Patch Retire Telegram", exc=exc, context=table)
        return False


def execute():
    for doctype in RETIRED_DOCTYPES:
        table = _table_for(doctype)

        if frappe.db.exists("DocType", doctype):
            try:
                frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
            except Exception as exc:
                log_exception("AIOS Patch Retire Telegram", exc=exc, context=doctype)

        if _has_rows(table):
            log_exception(
                "AIOS Patch Retire Telegram",
                context=f"{table} masih berisi baris; tabel tidak di-drop, perlu keputusan owner",
            )
            continue

        try:
            frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table}`")
        except Exception as exc:
            log_exception("AIOS Patch Retire Telegram", exc=exc, context=f"drop {table}")

    frappe.db.commit()
