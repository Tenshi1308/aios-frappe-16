# AIOS V1 (Frappe 16 / ERPNext) Rules

## 1. Error Logging Frappe
- Setiap `except` wajib panggil `frappe.log_error(title="...", message=frappe.get_traceback())`.
- Return JSON error sendiri (HTTP 200) tidak otomatis masuk `Error Log` → wajib log manual.
- Jaga CI tetap hijau: `ruff` (`S110`, `BLE001`, `B904`) + AST check di `test_repo_hygiene.py`.

## 2. Arsitektur Site-Level Multi-Tenant & Skema via Hooks
- **1 Client = 1 Site (`dns_multitenant`):** Isolasi tenant berada di level *Site* (database terpisah per klien). Registrasi mandiri tidak langsung membuka instance siap pakai (`aios_status = "Pending Provisioning"`, `enabled = 0`, `send_welcome_email = 0`, `flags.no_welcome_mail = True`, dijaga `on_login` & `auth_hooks`).
- **Tanpa `AIOS Tenant` (Semua di `User` + `AIOS Setting`):** Atribut operasional user (`aios_persona` (`Select`), `aios_persona_context` (`Small Text`), `aios_status` (`Select`), `aios_company_name` (`Data`), `aios_token_limit` (`Int`), `aios_tokens_used` (`Int`)) menempel langsung di `User`. Update `aios_tokens_used` wajib atomik via SQL/`frappe.qb` (dilarang `user_doc.save()`).
- **Custom Field & Custom DocPerm via `after_install` & `after_migrate` (Bukan `fixtures`):** Seluruh Custom Field di `User` (`create_custom_fields` + `frappe.db.updatedb("User")`), Role (`AIOS Admin`, `AIOS Client` `desk_access=0`), Role Profile, dan `Custom DocPerm` (`read=1, report=1` untuk `AIOS Client` pada DocType ERPNext target) wajib di-script pada hook `after_install` dan `after_migrate` di `hooks.py`. Dilarang memakai `fixtures` JSON atau mutasi `doc.append("fields", ...)` ke `tabDocField`.

## 3. Primitif Dinamis & Larangan Hardcode
- Mata uang: `frappe.db.get_value("Country", country, "default_currency")`.
- Template COA: `get_charts_for_country(country)`.
- Company aktif di site (100% site-level): `frappe.db.get_single_value("AIOS Setting", "default_company") or frappe.db.get_single_value("Global Defaults", "default_company")` (dilarang `frappe.db.get_default` karena per-user).
- Pembacaan dokumen di tool/plugin wajib menyertakan `frappe.get_doc(dt, name, check_permission="read")`.
- Kuota default user: baca dinamis dari `frappe.db.get_single_value("AIOS Setting", "default_user_token_limit")`.
- Dilarang fallback user/tenant tanpa sesi (`else 1`/`else 2`).

## 4. Isolasi Database pada Test
- **Wajib Dummy (`_Test ...`):** dilarang menyentuh `Company` atau `User` nyata yang sudah ada.
- **Test PoC (`#4d`, `#8`):** wajib 100% Read-Only (`SELECT` / `get_list` / `count`).
- **Guard `db.commit`:** monkeypatch `frappe.db.commit` jadi *no-op* selama test + `rollback()` di `tearDown`.
- Dilarang memanggil `frappe.db.commit()` di dalam file `test_*.py`.

## 5. Disiplin Riset & Verifikasi
- **Urutan sumber fakta:** `docs.frappe.io` (fetch) → `discuss.frappe.io` → source `apps/frappe` **terakhir**.
  Jangan menurunkan perilaku framework dari source bila dokumentasi resmi menjawab. Fetch, bukan clone.
- **Tanya manusia bila ada di sesi** (status proses, keputusan produk). Jangan menebak dari mtime atau log.
- **Ukur sekali, lalu pegang.** Dilarang mengulang pengukuran yang sama. Bila dua hasil bertentangan,
  resolusi sekali — bukan mengukur ketiga kalinya.
- **Jangan install yang sudah ada.** `frappe`, `erpnext`, `python`, `uv`, `bench`, site + DB sudah tersedia.
  Dilarang `pip install frappe` / `apt-get` / `uv tool`. Bila meragukan env, buktikan dulu kekurangannya.
- **Sebelum mengukur, jawab:** fakta ini mengubah keputusan apa? Bila tidak, tidak perlu diukur.

## 6. Otoritas Spesifikasi
- **`docs/` adalah source of truth**, bukan kode di repo. Kode ini kondisi rusak yang sedang
  diperbaiki menuju `docs/`. Bila kode ≠ `docs/`, yang diubah adalah kode.
- Kode hanya bahan mentah: `docs/05` §5/§8 yang memutuskan bagian mana yang diselamatkan.
- Verifikasi hasil Builder = kesesuaian dengan `docs/` & `AGENTS.md`, **bukan** dengan perilaku lama.
- Angka kondisi sekarang (mis. `746` error ruff, `149/11` smoke import) adalah **deskripsi**,
  bukan target yang dipertahankan.
