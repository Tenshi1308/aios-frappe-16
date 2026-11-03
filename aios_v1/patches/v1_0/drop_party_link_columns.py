"""Hapus kolom party_link_key dan party_link_expires_on dari tabAIOS Channel Thread.

Latar belakang (Batch 1 fondasi konektor):
Gate customer dibatalkan demi model chat customer langsung (tanpa tautan/kode).
Kolom `party_link_key` dan `party_link_expires_on` yang sempat dibuat di skema
dihapus dari tabel database.

Pengaman:
Sebelum kolom di-drop, patch memeriksa apakah ada nilai bukan kosong di kedua
kolom. Bila ditemukan nilai pada thread selain demo/test, patch berhenti (raise)
dan melaporkan agar tidak terjadi penghapusan data secara buta.
"""

from __future__ import annotations

import frappe

from aios_v1.lib.error_utils import log_exception

DOCTYPE = "AIOS Channel Thread"
TABLE = f"tab{DOCTYPE}"
TARGET_COLUMNS = ("party_link_key", "party_link_expires_on")


def _is_demo(row: dict) -> bool:
    ext = str(row.get("external_thread_id") or "")
    name = str(row.get("name") or "")
    disp = str(row.get("display_name") or "").lower()
    return (
        ext in {"164", "99001122", "99003344"}
        or name == "164"
        or "demo" in disp
        or "test" in disp
    )


def execute():
    if not frappe.db.table_exists(DOCTYPE):
        return

    existing_cols = [col for col in TARGET_COLUMNS if frappe.db.has_column(DOCTYPE, col)]
    if not existing_cols:
        return

    # Pengaman: periksa nilai tidak kosong di kolom target
    checks = []
    if "party_link_key" in existing_cols:
        checks.append("(party_link_key IS NOT NULL AND party_link_key != '')")
    if "party_link_expires_on" in existing_cols:
        checks.append("party_link_expires_on IS NOT NULL")

    where_clause = " OR ".join(checks)
    select_fields = ["name", "external_thread_id", "display_name", *existing_cols]
    fields_sql = ", ".join(f"`{f}`" for f in select_fields)

    try:
        rows = frappe.db.sql(
            f"SELECT {fields_sql} FROM `{TABLE}` WHERE {where_clause}",
            as_dict=True,
        )
    except Exception as exc:
        log_exception("AIOS Patch Drop Party Link Columns", exc=exc, context="query check")
        raise

    if rows:
        frappe.log_error(
            title="AIOS Patch Party Link Found",
            message=f"Nilai party_link terdeteksi pada baris: {rows}",
        )
        non_demo = [r for r in rows if not _is_demo(r)]
        if non_demo:
            msg = (
                f"Terdapat nilai party_link aktif pada thread non-demo: {non_demo}. "
                "Migrasi dihentikan untuk mencegah kehilangan data."
            )
            log_exception("AIOS Patch Drop Party Link Columns", context=msg)
            raise frappe.ValidationError(msg)

    # Drop kolom secara aman dan idempoten
    for col in existing_cols:
        try:
            frappe.db.sql_ddl(f"ALTER TABLE `{TABLE}` DROP COLUMN `{col}`")
        except Exception as exc:
            log_exception("AIOS Patch Drop Party Link Columns", exc=exc, context=f"drop {col}")
            raise

    frappe.db.commit()
