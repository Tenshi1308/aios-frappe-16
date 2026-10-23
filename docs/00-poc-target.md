# 00 — Target PoC AIOS V1 (Kontrak Acuan)

**Status:** kontrak scope PoC, 2026-10-22. **Baca dokumen ini pertama.**
**Sifat:** acuan scope/prioritas, bukan spesifikasi perilaku. Perilaku produk tetap di `docs/01`–`docs/04`; desain UI di `docs/08`; status eksekusi di `docs/05.1` §1.

Dokumen ini menjawab tiga hal yang paling sering ditanyakan ulang:

1. PoC selesai bila apa?
2. Apa yang masuk dan apa yang tidak masuk PoC?
3. Istilah yang dipakai di dokumen lain artinya apa?

---

## 1. Definisi PoC

**PoC AIOS V1** adalah satu site klien dengan data ERPNext Sales/Finance yang bisa dipakai orang bisnis dari awal sampai akhir:

> user `AIOS Client` login ke **Ekasa Desk** (Vue), membuka modul Sales/Finance, berdialog dengan tim agent, agent membaca data ERPNext lewat plugin, menyusun draft transaksi, manusia menyetujui, dokumen benar-benar masuk ERPNext, semua langkah terlihat di **Live Agent Trace**, file/artefak tersimpan di **workspace private**, token/biaya tercatat, dan `AIOS Admin` mengelola site/user/kuota dari **Developer Control Plane**.

PoC **bukan** “semua fitur di docs selesai”. PoC adalah alur end-to-end di atas yang terbukti jalan.

---

## 2. Scope final PoC

### 2.1 Wajib PoC

| Item | Peran di PoC |
|---|---|
| `#13` | Hapus adapter DB eksternal; ERPNext-first. **Sudah selesai.** |
| `#4a-1` | Fondasi skema & permission (`AIOS Token Usage`, field site, matriks `Custom DocPerm`). |
| `#4a-2` | Hapus `AIOS Tenant` & sisa relasi `tenant`; ownership per `User`. |
| `#7b` | Token accounting & approval (L8–L9). |
| `#4d` | Seed data ERPNext untuk demo Sales/Finance. |
| `#8` | Tool ERPNext wrapper + loop agent; **di sini agent mulai bisa bertindak**. |
| `H2` | Plugin & MCP Manager + 7 built-in plugin; agent punya tool lengkap dan terkontrol. |
| `H3` | Developer Control Plane = **`#11`**. |
| `H4` | Deep Finance/Sales agents: delegasi nyata, 5 event trace, token atomik = **pendalaman `#8`**. |
| `H5` | Isolated workspace/artefak: **sandbox file** berbasis Private `File`. |
| `#12` | Ekasa Desk Vue (frontend baru). |

### 2.2 Pendukung (bukan gate PoC)

`#4b`/`#4c` (identitas/auth), `#5` (kuota site & user), `#6` (konstanta), `#9` (dispatcher router), `#10` (status docs), `#2`/`#3` (higiene repo). Boleh selesai sebelum/sesudah PoC selama tidak merusak alur utama.

### 2.3 Di luar PoC

- `H1` — multi-provider & per-agent model routing. **Ditunda**; PoC cukup satu model. `docs/02` tetap target arsitektur jangka panjang, bukan syarat PoC.
- Billing/tiering, domain/SSL per site, isolasi OS/container.
- Kedalaman 9 divisi; PoC fokus **Sales + Finance (Order-to-Cash)**.
- Server MCP eksternal untuk ERPNext (skema tool boleh dipinjam, server tidak dipakai).
- Frontend Next.js lama; akan diganti Vue.

### 2.4 Jangan menghitung dua kali

- `H3` = `#11`.
- `H4` = pendalaman `#8`.
- `H1` tidak dikerjakan untuk PoC.
- `H2`/`H5` bukan “nice-to-have”; keduanya wajib.

---

## 3. Acceptance end-to-end

PoC dinyatakan selesai bila semua poin ini bisa diamati:

1. **Data:** site klien punya Company, Item, Customer, Sales Order, Sales Invoice, dan GL Entry demo.
2. **Login & UI:** `AIOS Client` login ke Ekasa Desk Vue; modul Sales/Finance terbuka; data ERPNext tampil read-only; `company` dipaksa server.
3. **Agent & tool:** agent memakai 7 plugin (H2), membaca ERPNext lewat `erpnext-core-data`/`erpnext-financial-reports`; tidak ada SQL/DB eksternal.
4. **Delegasi & trace:** Orchestrator mendelegasikan ke sub-agent; 5 event SSE tampil di Live Agent Trace; system prompt internal tidak tampil.
5. **Draft & approval:** agent membuat `Pending Action Draft` (`CREATE`/`UPDATE_DRAFT`/`CANCEL_AND_AMEND`) dengan before → after; belum ada tulisan ke ERPNext.
6. **Approve → posting:** manusia Approve; dokumen ERPNext terbentuk; dokumen `submitted` tidak diedit/dihapus; koreksi lewat `CANCEL_AND_AMEND`.
7. **Token & biaya:** pemakaian token tercatat per user/agent/site; kuota dicek; biaya bisa dihitung.
8. **Workspace:** file/artefak dibuat lewat Private `File` terikat `AIOS Conversation`; user lain tidak bisa akses; nama file disanitasi; artefak tampil sebagai jendela desktop.
9. **Control plane:** `AIOS Admin` bisa melihat site, menyetujui user pending (hanya role `AIOS Client`), mengatur kuota, monitoring agregat.
10. **Keamanan & izin:** `AIOS Client` read-only ERPNext; `AIOS Control` hanya read `User` + `AIOS Token Usage`, plus satu endpoint sync konfigurasi yang sempit; tidak ada `AIOS Admin` di site klien; `Administrator` tidak tersentuh.

> **Catatan implementasi (2026-10-23):** `#8` baru menutup `CREATE`; `UPDATE_DRAFT` dan `CANCEL_AND_AMEND` dikerjakan di H4. Acceptance #5–#6 terpenuhi penuh setelah H4.

---

## 4. Urutan pengerjaan

Urutan tahap, item, dan status ada di [`docs/05.1` §1](./05.1-roadmap-perbaikan-fondasi.md).

---

## 5. Glossary

| Istilah | Arti |
|---|---|
| **AIOS Admin** | Role operator di **site developer**. `desk_access=0`; tidak dipasang di site klien. |
| **Administrator** | Root Frappe. Satu-satunya yang memakai **Frappe Desk** untuk setup/operasi darurat. Tidak pernah dimodifikasi. |
| **AIOS Control** | Role layanan di **site klien**. Tanpa login manusia; `read` `User` + `AIOS Token Usage`, plus satu endpoint sync konfigurasi yang sempit; tanpa akses DocPerm umum ke `AIOS Setting`/ERPNext. |
| **AIOS Client** | User bisnis di site klien. `Website User`, `desk_access=0`; memakai **Ekasa Desk**. |
| **AIOS Setting** | Config site: company, kuota site, konteks bisnis, dan **satu model LLM** untuk PoC. |
| **AIOS Token Usage** | DocType log pemakaian token/biaya per panggilan. Tidak ada link `conversation`. |
| **AIOS LLM Provider** | Registry multi-provider (H1). **Tidak dipakai di PoC**; PoC single model di `AIOS Setting`. |
| **AIOS Agent Model Route** | Mapping agent → provider/model (H1). **Ditunda** untuk PoC. |
| **Frappe Desk** | UI admin bawaan Frappe (`/app`). Bukan UI produk AIOS. |
| **Ekasa Desk** | Desktop OS produk AIOS (Vue, `docs/08`). |
| **Control Plane** | Site Frappe khusus developer untuk mengelola banyak site klien, sekaligus sumber kebenaran konfigurasi operator (model, provider, plugin). |
| **Client Site** | Satu site/DB per klien (`1 Client = 1 Site`). |
| **Sandbox** | Batas eksekusi agent: tanpa shell, tanpa jaringan bebas, tanpa file server di luar `File`, tanpa SQL, identitas tak bisa dipalsukan, delegasi maks. 2, tulis ERPNext lewat approval. |
| **H1–H5** | Tahap di `docs/06`; H1 ditunda, H2–H5 masuk PoC. |
| **`#n`** | Item roadmap di `docs/05.1`. |

---

## 6. Keputusan yang mengikat (decision log)

| Tanggal | Keputusan |
|---|---|
| 2026-10-22 | Target PoC = fondasi + `#8` + H2 + H3 + H4 + H5 + `#12`; **H1 skip**. |
| 2026-10-22 | `H3` = `#11`; `H4` = pendalaman `#8`; jangan dikerjakan dua kali. |
| 2026-10-22 | `H2` wajib PoC: plugin manager + 7 built-in plugin; tanpa H2 agent cuma punya 3 plugin ERPNext. |
| 2026-10-22 | `H5` wajib PoC: sandbox file/workspace Private `File`; bukan demo opsional. |
| 2026-10-22 | PoC satu model; config di `AIOS Setting`. UI provider/model nanti di `#11` (frontend baru), bukan `#4a-1`. |
| 2026-10-22 | `AIOS Admin` `desk_access=0`, hanya site developer; site klien hanya `AIOS Client` + `AIOS Control` + `Administrator`. |
| 2026-10-22 | `AIOS Token Usage` tanpa link `conversation`; field: `user`, `provider`, `model`, `branch`, `agent`, `input_tokens`, `output_tokens`, `total_tokens`, `cost`. |
| 2026-10-22 | `AIOS Token Usage.cost` dalam IDR. |
| 2026-10-22 | `AIOS Admin` tidak dibuat per client site; hanya control plane di `#11`. |
| 2026-10-22 | Setup wizard Frappe diselesaikan job provisioning `#11`; client tidak pernah melihat/mengisi wizard atau memakai `Administrator`. |
| 2026-10-22 | `AIOS Tenant` dihapus; scope tenant diganti `user`; `1 Client = 1 Site`. |
| 2026-10-22 | `System Manager` tidak boleh write/create/delete `AIOS Setting`; hanya `Administrator`. |
| 2026-10-22 | Antrean pending wajib filter role `AIOS Client`; `Guest`/`Administrator` tidak boleh muncul. |
| 2026-10-22 | `User.aios_status` tidak punya default; registrasi mengisi eksplisit. |
| 2026-10-22 | Kuota PoC = satu gerbang site: `AIOS Setting.site_token_limit` vs `site_tokens_used`; `User.aios_token_limit` **bukan** gerbang (dihapus di `#5`), `User.aios_tokens_used` = statistik harian; counter site + user di-reset harian, ledger `AIOS Token Usage` tetap. |
| 2026-10-22 | Status `Pending Action Draft`: `PENDING_APPROVAL` → `APPROVED` → `EXECUTED` (hanya setelah dokumen ERPNext dibuat) / `REJECTED` / `EXPIRED`; `COMPLETED` dihapus. |
| 2026-10-23 | Konfigurasi operator (model LLM, provider, plugin) **global lintas semua site klien**: satu sumber kebenaran di site developer, disalin ke tiap site klien lewat Control API (bentuk *push*). Semua klien memakai konfigurasi yang sama; tidak ada override per site maupun per user. Konsekuensi yang diterima: kredensial LLM terkonsentrasi di database developer. |
| 2026-10-23 | `#8` menutup `CREATE` saja; `UPDATE_DRAFT` dan `CANCEL_AND_AMEND` dipindah ke H4. Loop tool maksimal 6 putaran; event tool call Orchestrator tidak dikirim di `#8`. |

---

## 7. Known gaps (status kode, bukan target)

| Gap | Dampak |
|---|---|
| `AIOS Setting` JSON masih kurang `max_users` | `company_context_persona` sudah ada sejak `#8`; `max_users` menyusul `#5`. `default_user_token_limit` dibatalkan (kuota per user tidak dipakai). |
| `AIOS Admin` role/profile lama masih ada di site existing (`desk_access=0`, tanpa DocPerm); tidak dibuat di site baru | Role/profile control plane menyusul `#11`. |
| ~~`/api/monitoring` masih pakai `AIOS Tenant`~~ | ✅ Dipindah ke `User` + `AIOS Token Usage` di `#4a-2`. |

---

## 8. Cara baca untuk agent

1. **`docs/00` (dokumen ini)** — target & scope.
2. **`docs/05.1` §1** — status nyata tiap item.
3. **`docs/README.md`** — indeks & klasifikasi dokumen.
4. **`docs/01`–`docs/04`, `docs/08`** — spesifikasi perilaku/UI sesuai kebutuhan.
5. **`docs/06`** — detail H2–H5; **H1 ditunda**, jangan mulai dari sini.

> Jangan mulai dari `docs/06` tanpa membaca `docs/00`. `docs/06` adalah detail tahap, bukan definisi target PoC.
