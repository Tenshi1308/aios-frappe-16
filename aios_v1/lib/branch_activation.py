"""Aktivasi cabang per client (level site) — sumber tunggal kebenaran.

Arsitektur AIOS V1 adalah `1 Client = 1 Site` (docs/05.2), jadi "cabang yang
diambil client" adalah konfigurasi level site, bukan kolom per user. DocType
`AIOS Branch Activation` (Single) menyimpan daftar cabang beserta status
aktifnya; modul ini satu-satunya pembaca, dengan cache + invalidasi on_update.

Kontrak yang dijaga:
- `is_branch_active(branch_key)` dipakai `plugin_manager.registry` sebagai
  pengganti `_PRIORITY_BRANCHES`, sehingga tanda tangan `get_branches` dan
  `is_branch_enabled` tidak berubah dan 20 titik pemanggil tidak tersentuh.
- Fail-closed: bila DocType belum ada atau barisnya kosong, tidak ada cabang
  yang aktif (keputusan Ten D5 untuk site baru).
"""

from __future__ import annotations

import frappe

DOCTYPE = "AIOS Branch Activation"
ITEM_DOCTYPE = "AIOS Branch Activation Item"
CACHE_KEY = "aios:branch_activation"
CACHE_TTL_SECONDS = 300

# Cabang yang punya aktivasi per client (keputusan Ten D13). Hanya cabang
# priority Lapis B yang sudah punya agent, domain, dan tool.
ACTIVATABLE_BRANCHES = ("sales", "finance", "accounting", "purchasing")

# Site yang sudah ada sebelum fitur ini: default 4 cabang aktif (D4). Site baru
# disemai kosong oleh after_install (D5).
LEGACY_DEFAULT_BRANCHES = ACTIVATABLE_BRANCHES


def get_active_branches() -> frozenset[str]:
    """Return kumpulan branch_key yang aktif untuk site ini (fail-closed)."""
    # Cache Redis tidak ikut rollback DB, jadi di dalam tes nilainya bisa
    # tertinggal dari baris yang sudah di-rollback. Baca langsung saat tes.
    if getattr(frappe.flags, "in_test", False):
        return _read_active_branches()
    cached = frappe.cache.get_value(CACHE_KEY)
    if isinstance(cached, (list, tuple)):
        return frozenset(str(item) for item in cached)
    branches = _read_active_branches()
    frappe.cache.set_value(CACHE_KEY, sorted(branches), expires_in_sec=CACHE_TTL_SECONDS)
    return branches


def is_branch_active(branch_key: str) -> bool:
    """True bila cabang aktif untuk site ini; False untuk key tak dikenal."""
    if not isinstance(branch_key, str):
        return False
    key = branch_key.strip().lower()
    if not key:
        return False
    return key in get_active_branches()


def clear_cache() -> None:
    """Hapus cache resolver. Dipanggil on_update DocType dan oleh tes."""
    frappe.cache.delete_value(CACHE_KEY)
    # Frappe menyimpan cache lokal per request di frappe.local; bersihkan juga
    # agar nilai lama tidak bertahan di proses yang sama (mis. worker/tes).
    local_cache = getattr(frappe.local, "cache", None)
    if local_cache is not None:
        try:
            local_cache.delete_value(CACHE_KEY)
        except Exception as exc:
            from aios_v1.lib.error_utils import log_exception

            log_exception("AIOS Branch Activation Cache", exc=exc, context="clear_cache local")


def visible_branch_keys() -> frozenset[str]:
    """Kunci cabang yang boleh tampil di riwayat (D6: sembunyikan, jangan hapus)."""
    return get_active_branches()


# D11: bidang yang punya detektor proaktif, beserta label tampilannya. Hanya
# Sales yang punya detektor hari ini; Finance/Accounting/Purchasing ditambahkan
# di sini saat detektornya ada — tab Insight Proaktif muncul sendiri.
PROACTIVE_BRANCHES = (("sales", "Sales"),)


def get_proactive_branches() -> list[dict]:
    """Bidang aktif yang punya proaktif, untuk pengelompokan tab (D11)."""
    active = get_active_branches()
    return [
        {"branch": branch_key, "label": label}
        for branch_key, label in PROACTIVE_BRANCHES
        if branch_key in active
    ]


def _read_active_branches() -> frozenset[str]:
    """Baca baris aktif langsung dari child table (satu query, tanpa get_single).

    `frappe.get_single` memuat seluruh dokumen dan memicu `frappe.get_all`;
    query langsung lebih murah dan tidak bergantung pada dokumen induk.
    """
    if not frappe.db.exists("DocType", DOCTYPE):
        return frozenset()
    # Query SQL langsung: `frappe.db.get_all` dipakai sebagian tes sebagai titik
    # patch untuk dokumen lain, dan resolver ini tidak boleh ikut tertangkap.
    rows = frappe.db.sql(
        """
        SELECT branch_key
        FROM `tabAIOS Branch Activation Item`
        WHERE parenttype = %(parenttype)s
          AND parentfield = 'branches'
          AND enabled = 1
        """,
        {"parenttype": DOCTYPE},
        as_dict=True,
    )
    return frozenset(
        str(row.get("branch_key")).strip().lower()
        for row in rows
        if str(row.get("branch_key") or "").strip()
    )


def seed_branch_activation(branches=None) -> bool:
    """Semai DocType sekali saja; kembalikan True bila menulis.

    Mengikuti pola `setup.ensure_builtin_plugins`: idempoten dan tidak menimpa
    state operator. Flag `seeded` dipakai, bukan "daftar kosong", supaya
    operator yang sengaja mematikan semua cabang (D5) tidak diisi ulang oleh
    migrate berikutnya.
    """
    if not frappe.db.exists("DocType", DOCTYPE):
        return False
    doc = frappe.get_single(DOCTYPE)
    if int(doc.get("seeded") or 0):
        return False
    # D5: `branches=()` berarti sengaja kosong (site baru), bukan "pakai default".
    # Hanya `None` yang berarti pemanggil tidak menentukan daftar (site lama/D4).
    if branches is None:
        branches = LEGACY_DEFAULT_BRANCHES
    for branch_key in branches:
        doc.append("branches", {"branch_key": branch_key, "enabled": 1})
    doc.seeded = 1
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    clear_cache()
    return True
