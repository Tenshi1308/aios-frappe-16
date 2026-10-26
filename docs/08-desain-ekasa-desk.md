# 08 — Desain Ekasa Desk (Antarmuka Desktop OS)

Dokumen ini menetapkan desain antarmuka klien AIOS: **Ekasa Desk**, sebuah *desktop OS* di browser. Sifatnya **normatif** — kode menyesuaikan dokumen ini.

Kontrak harness (trace, tool, approval) ada di `docs/02` §3 dan `docs/04` Alur 5. Dokumen ini hanya mengatur **permukaan dan tata letaknya**.

---

## 1. Konsep & Prinsip

1. **OS, bukan halaman web.** Pengguna masuk lewat layar boot dan sign-in, lalu bekerja di desktop dengan taskbar, jendela, dan panel samping — bukan deretan menu.
2. **Agent adalah warga utama.** Panel agent selalu ada. Modul dan artefak muncul sebagai jendela di desktop.
3. **Modul tetap ada.** Daftar dokumen dan kartu angka adalah nilai jual: pengguna bisa melihat data ERPNext langsung tanpa bertanya ke AI. Agent juga bisa membukakan modul.
4. **Tanpa emoji dekoratif.** Ikon garis vektor dan badge tipografi saja.
5. **Nol hardcoded.** Nama agent, nama modul, doctype, company, kuota, dan prompt saran **tidak boleh** ditulis di berkas komponen — semuanya dari backend (§7).

---

## 2. Struktur Layar

### 2.1. Boot

Layar gelap penuh dengan progres bertahap: menyambung ke site, memulihkan sesi, mengambil `frappe.boot`, memuat workspace & izin, mendaftarkan agent, membuka kanal realtime, menyiapkan desktop. Progres harus mencerminkan langkah nyata, bukan animasi palsu.

### 2.2. Sign-In

Form email + password, ditambah tautan ke pendaftaran mandiri. Kegagalan menampilkan pesan aman (tanpa detail internal). Setelah sukses, lanjut ke desktop sesuai peran.

### 2.3. Desktop

- **Taskbar** di bawah: tombol mulai, pencarian, daftar agent, jam, indikator status koneksi.
- **Area desktop**: jendela-jendela yang bisa dibuka, dipindah, diperkecil, dan ditutup.
- **Flyout**: pencarian (`Ctrl+K`) dan daftar agent (`Ctrl+J`). `Esc` menutup.
- **Tema**: terang dan gelap, mengikuti preferensi sistem, bisa dipaksa lewat atribut tema.

### 2.4. Panel Agent

Menempel di sisi kanan. Berisi riwayat percakapan, composer, pemilih agent, dan **Live Agent Trace** (§3). Panel bisa dilebarkan dan ditutup lewat tombol X; saat ditutup, buka lagi dari taskbar atau `Ctrl+J`. Agent tetap inti produk, jadi tidak ada mode tanpa akses agent.

#### Lampiran chat

Composer menyediakan tombol paperclip untuk memilih dan mengunggah file, menampilkan progress, chip file, error, serta aksi hapus lampiran. Client tidak pernah menampilkan atau meminta user mengetik File ID; ID hanya menjadi state internal frontend untuk mengirim `file_ids`.

Upload membuat Private `File` dengan `owner = frappe.session.user` dan `is_private = 1`. Sebelum pesan dikirim, file tetap tertaut langsung ke `AIOS Conversation`; setelah dikirim, backend memakai attachment bawaan Frappe untuk menautkan File ke `AIOS Message` milik user. File yang dibuat agent juga ditautkan ke pesan agent. Conversation tetap dapat ditentukan lewat `AIOS Message.conversation`, tanpa schema baru. Request chat mengirim `file_ids`; backend memvalidasi kepemilikan, status private, percakapan induk, serta batas ukuran dan format yang diizinkan. Backend menyisipkan metadata file ke konteks model, lalu model dapat memanggil `document_extract(file_id)`; hasil ekstraksi tampil di chat.

File tampil sebagai chip langsung di bawah pesan yang mengunggah atau membuatnya. File lama yang masih tertaut langsung ke `AIOS Conversation` tidak dihapus dan ditampilkan dalam satu entri khusus di alur chat, dengan keterangan bahwa pesan asalnya tidak tercatat.

Backend menolak file milik user lain, file publik, file dari conversation lain, dan file yang melampaui batas ukuran atau format. Respons ke client tidak membocorkan isi file; File ID tidak boleh muncul di pesan error maupun event — ia hanya state internal frontend.

**Status backend:** endpoint upload `POST /api/chat/upload`, validasi `file_ids` sebelum konteks model dibentuk, dan binding `document_extract` ke conversation aktif tersedia sejak H5 fase 1 (`b07975f`). Revisi 46 menautkan unggahan dan file agent ke pesan terkait melalui attachment Frappe dan menjaga akses dokumen di cakupan conversation. **UI:** composer, chip lampiran, progress upload, dan aksi hapus chip (lokal) ada sejak #12 fase 1 (`a4f4113`); revisi 46 menampilkan chip file per pesan dan menyediakan entri untuk file historis tanpa pesan asal. Belum ada endpoint hapus lampiran.

**Acceptance:** client dapat melampirkan CSV, PDF, atau XLSX tanpa mengetik ID; model membaca isi file; file user lain ditolak; file publik ditolak.

---

## 3. *Live Agent Trace* di Panel Agent

Kontrak event ada di `docs/02` §3.1. Tata letaknya:

**Status implementasi:** H4 menyediakan event SSE backend untuk empat event delegasi, `trace_cross_branch`, dan `artifact_created`; #12 fase 2a menambah trace tool Orchestrator (`agent = "Orchestrator"`) serta kartu dari Sub-Agent. UI #12 fase 2a: blok trace **live di atas bubble jawaban** (bertumbuh tiap event, detail inline per langkah, mengecil jadi baris ringkas setelah `done`) dan jendela kartu persetujuan (get_draft + Setujui/Tolak + daftar draft pending `list_pending_drafts`; kartu dibuka setelah `done`). Jendela artefak file tetap menyusul (fase 2b).

1. **Selagi jawaban mengalir**, blok trace tampil **di atas bubble jawaban** bergaya *activity feed* (flat, seperti harness populer): header **"Working for …"** dengan timer hidup, tiap event menjadi **item berikon** (delegasi/peran, tool, hasil, konsultasi) dengan subteks ringkas dari argumen, durasi per item dihitung klien, dan item terakhir ber-status berjalan (spinner).
2. Setelah stream selesai, blok mengecil menjadi baris ringkas di atas jawaban: **jumlah langkah · token · durasi**, dengan tombol **Lihat detail**.
3. Expand menampilkan daftar item; **tiap item terbuka inline** di blok trace: instruksi tugas, nama tool, **argumen asli**, dan hasil.
4. Tidak ada jendela detail trace — semua detail inline; jendela desktop dipakai untuk Approval Card dan daftar persetujuan. Tidak ada item "thought" — model tidak mengirim reasoning via stream.

**Wajib:** instruksi tugas, argumen tool, dan hasil terlihat apa adanya.
**Dilarang:** menampilkan *system prompt* internal AIOS (ETHOS, guard, instruksi dasar).

---

## 4. Agent

Daftar agent berasal dari backend (`registry.py`), bukan dari berkas komponen. Setiap agent punya nama, deskripsi singkat, warna aksen, dan saran pertanyaan — semuanya dari API.

Agent dapat membuka modul dan membuat artefak. Aksi tulis **tidak pernah** langsung ke ERPNext: selalu lewat `Pending Action Draft` dan persetujuan manusia (`docs/04` Alur 5).

---

## 5. Artefak sebagai File & Jendela

File yang dibuat agent disimpan sebagai Private `File` (`docs/02` §3.2) dan tampil sebagai **berkas di desktop**. Approval Card H4 adalah event backend virtual; UI #12 fase 2a mengambil detail dari `get_draft` (jendela kartu dengan Setujui/Tolak, termasuk hasil gagal `executed:false` yang dijelaskan dengan code+message), daftar draft pending milik pemilik lewat `list_pending_drafts`, dan kartu tidak membuat `File`:

| Jenis | Tampilan |
|---|---|
| Approval Card | Event backend H4; jendela kartu persetujuan di UI #12 (prioritas tertinggi), tanpa `File` |
| Tabel & grafik | Jendela data interaktif |
| Dokumen eksekutif + Mermaid | Jendela dokumen, bisa cetak/ekspor PDF |
| Spreadsheet `.xlsx` / `.csv` | Jendela preview + unduh — **ter implement #12 fase 2b (diperkaya)**: `.csv` dirender sebagai **tabel** (Papa Parse, header sticky), `.md` dirender **markdown** (markdown-it `html:false` + DOMPurify), `.pdf` embed iframe, `.xlsx` dirender sebagai **tabel** (SheetJS, sheet pertama), format lain hanya metadata + unduh; file > 2 MB tidak di-fetch; tombol unduh memakai `file_url` |
| Presentasi HTML | Jendela slide terisolasi |

Berkas yang dibuat pada satu percakapan hanya terlihat oleh pemilik percakapan tersebut. **Status backend (H5 fase 1, `b07975f` + revisi 46):** file privat `.csv`/`.xlsx`/`.md`/`.pdf` dibuat oleh `workspace_create_file`, dikaitkan dengan pesan agent melalui relasi attachment Frappe, dan event `artifact_created` (`FILE`) dikirim backend. File yang diunggah user dikaitkan ke pesan user saat dikirim; unggahan yang belum dikirim dan file historis tetap tertaut langsung ke conversation. Relasi pesan dan chip file tersimpan di server, sehingga tampil lagi setelah reload. **Jendela artefak FILE ada di #12 fase 2b** (chip dibuka manual, tidak auto-open saat event; pratinjau `.csv`/`.xlsx` tabel, `.md` markdown tersanitasi, `.pdf` embed iframe; file > 2 MB tanpa fetch). **Bubble jawaban agent merender markdown penuh** (markdown-it `html:false` + DOMPurify via `v-html` — persetujuan owner mengganti guard no-v-html lama). Grafik interaktif, Mermaid, dan iframe presentasi menyusul.

File yang sudah ada sebelum relasi per pesan diterapkan tetap ditampilkan sebagai entri “File lama dari percakapan ini; pesan asal tidak tercatat.” Sistem tidak memindahkan byte file atau menghapus/mengubah file lama secara destruktif.

### File Explorer

Jendela **Files** menyediakan Explorer baca-saja dengan tree virtual `root → cabang → percakapan → file`. Tree dibentuk dari `AIOS Conversation` dan `File`; ini representasi relasi percakapan, bukan struktur folder fisik. File tetap berada di `Home/Attachments`. Explorer menampilkan semua file percakapan yang dimiliki user, termasuk unggahan lampiran dan artefak agent, karena DocType `File` tidak membedakan kedua asal tersebut.

Backend hanya mengembalikan file privat milik user yang terikat ke percakapan miliknya, dan mengecualikan baris folder. Payload listing Explorer dan detail percakapan boleh memuat `file_id` (`File.name`) sebagai identitas row internal; UI tidak menampilkannya. `file_url` tetap locator yang dipakai jendela `ArtifactWindow` untuk preview dan unduh. Payload tidak memuat path filesystem atau isi file. Event SSE `artifact_created` tetap tidak memuat `file_id`.

Explorer tidak mengubah, memindahkan, menghapus, atau membagikan file. Unduh memenuhi kebutuhan share. Rename dan hapus file adalah fase berikut dan memerlukan mutasi `File` serta audit trail.

---

## 6. Modul

Modul menampilkan **daftar dokumen** dan **kartu angka** dari ERPNext. Datanya dibaca langsung dari ERPNext site klien dengan izin user yang sedang login — tidak ada database perantara.

- Modul dibuka dari Start Menu (dikelompokkan per `group`: `Sales` / `Finance`), pencarian (`Ctrl+K`), **atau** oleh agent saat diminta ("buka Sales Invoice" → event SSE `open_module`).
- Katalog modul server-owned (`aios_v1/lib/desktop_modules.py`) menyediakan 7 modul: `sales_invoice`, `sales_order`, `purchase_invoice`, `payment_entry`, `customer`, `supplier`, `item`. Daftar modul, ikon semantik, grup, doctype, kolom, filter, dan definisi kartu berasal dari backend (§7).
- Jendela modul (`desk/src/components/module/ModuleWindow.vue`, window ID `module:<key>`) merender header + tombol refresh, kartu agregat (`label`, `value`, `currency` bila `format == "currency"`, `scope`: `company` | `site`), form filter sesuai deklarasi `module.filters` (`date_from`, `date_to`, `status`, `party` — hanya yang dikirim backend), tabel dengan kolom dari respons server, serta navigasi halaman prev/next.
- Modul bersifat **baca saja**. Penulisan tetap lewat approval.
- Angka pada kartu adalah agregat yang dihitung server (`COUNT`/`SUM`), bukan dihitung di browser; klien hanya memformat angka/mata uang/tanggal untuk tampilan. Refresh modul mempertahankan data lama di layar selagi pemuatan berlangsung.

### 6.1. Jendela Pengaturan (*Settings*)

Jendela **Pengaturan** (`desk/src/components/windows/SettingsWindow.vue`, window ID `settings`, dibuka dari Start Menu) menampilkan informasi akun dan kuota secara **baca saja** tanpa form input atau aksi mutasi:

- **Profil pengguna:** `name` (`User.full_name` atau `user`), `persona` (`User.aios_persona`), dan `status` (`User.aios_status`).
- **Company aktif:** `name` dan `currency` dari company tingkat site (`AIOS Setting.default_company` / `Global Defaults`).
- **Kuota site:** menampilkan plafon tingkat site (`AIOS Setting.site_token_limit` dan `site_tokens_used`, bukan per user) dengan label eksplisit **Kuota site**, progress bar (`percent_used`, dibatasi 100% untuk lebar bar), nilai `terpakai / limit`, serta `remaining` (bernilai `null` bila `limit <= 0`).
- **Jadwal reset kuota site:** waktu reset berikutnya diambil server dari method internal Frappe `ScheduledJobType.get_next_execution()` untuk job `aios_v1.services.usage.reset_daily_counters` (method internal scheduler Frappe, bukan API publik, dipakai agar tidak menduplikasi parsing cron). Karena keduanya berzona waktu naive site (`Asia/Jakarta`), server menghitung `seconds_remaining` (`int`) dan `at_label` (`HH:mm`) sehingga browser tidak menafsirkan ulang zona waktu dari string ISO. Scheduler Frappe memeriksa antrean tiap `DEFAULT_SCHEDULER_TICK = 4 * 60` detik (4 menit sejajar kelipatan jam), sehingga eksekusi nyata berlangsung 0–4 menit setelah `00:00`; ketika hitung mundur mencapai `0`, UI menampilkan **"Menunggu reset berikutnya"**. Bila scheduler tidak aktif (`is_scheduler_inactive(verbose=False)`) atau job tidak ditemukan (`source === "unknown"` / `at === null`), UI wajib menampilkan peringatan **"Reset belum terjadwal"** tanpa angka hitung mundur.
- **Kerahasiaan `AIOS Setting`:** endpoint `desktop.settings` hanya membaca `site_token_limit` dan `site_tokens_used` lewat `get_single_value`; field sensitif/konfigurasi internal (`api_key`, `company_context_persona`, `system_ethos`, `model_name`, `base_url`, `temperature`) tidak pernah disertakan dalam respons maupun direferensikan di komponen UI.
- **Adapter API (`@modules-api`):** pemilihan adapter dilakukan saat build di `desk/vite.config.ts` lewat `VITE_DESKTOP_ADAPTER=real|mock` (default `real`), di mana `desk/src/api/modules.ts` dan `desk/src/api/mock/modules.ts` keduanya memenuhi kontrak TypeScript `ModulesApi` (`satisfies ModulesApi`) tanpa impor `api/mock` di bundle produksi.

---

## 7. Aturan *Zero Hardcoded*

| Data | Sumber |
|---|---|
| Daftar agent, nama, deskripsi, saran prompt | Backend (`registry.py`) |
| Daftar modul, ikon, warna, doctype | Backend |
| Company aktif, mata uang | `AIOS Setting` |
| Kuota & pemakaian token | `AIOS Setting.site_token_limit` (gerbang), `User.aios_tokens_used` (statistik) |
| Versi & URL API | `frappe.boot` / environment |

**Aturan yang bisa diuji:** tidak ada nama agent, nama modul, atau nama doctype yang ditulis sebagai teks di berkas komponen. Data contoh hanya boleh hidup di lapisan `api/mock/` dan tidak pernah diimpor jalur produksi.

Endpoint `/api/branches` memproyeksikan data di server untuk tampilan saja: cabang mengirim `key`, `name`, `description`, `tagline`, `enabled`; worker mengirim `key`, `branch`, `jobRole`, `description`, `exampleQuestions`, `enabled`. Materi prompt internal tidak pernah dikirim ke browser.

**Aturan yang sama berlaku untuk gaya:** komponen dilarang menulis warna, font, bayangan, atau radius secara langsung. Semua lewat token (§8).

---

## 8. Token Visual & CSS

Dua lapis token di `styles/tokens.css`:

1. **Primitives** — nilai mentah (hex, px, font). Hanya boleh dipakai di berkas token.
2. **Semantic** — `--surface`, `--text`, `--accent`, `--ok`, `--warn`, `--bad`, `--shadow`, `--radius`. Inilah yang dipakai komponen.

Yang dijadikan token: warna, font family/ukuran/weight, radius, bayangan, blur, skala spasi, z-index, durasi animasi, tinggi taskbar, lebar panel.

Yang **tidak** perlu token: nilai sekali pakai seperti lebar kolom tabel di satu tempat.

**Pemeriksaan otomatis:** `grep -rE "#[0-9a-fA-F]{3,6}|rgba?\(" src/components/ src/views/` harus kosong.

**Gaya penulisan:** CSS *scoped* per komponen. **Tailwind tidak dipakai** — desain sudah final dan efek visualnya (glass, gradient, shadow berlapis) lebih tepat ditulis langsung.

**Aset lokal:** font dan Vue di-*bundle* sendiri. Aplikasi harus jalan tanpa internet.

---

## 9. Stack & Struktur Folder

| Bagian | Pilihan |
|---|---|
| Build | Vite |
| Framework | Vue 3 |
| Bahasa | TypeScript |
| Router | Vue Router |
| State | Pinia |
| CSS | CSS variables + scoped (tanpa Tailwind) |

```
desk/
├── index.html
├── vite.config.ts
├── tsconfig.json
└── src/
    ├── main.ts
    ├── App.vue
    ├── router/index.ts
    ├── stores/          session · agents · modules · conversations
    ├── api/
    │   ├── client.ts    frappe.call + CSRF
    │   ├── desktop.ts   bootstrap · module · list · search
    │   ├── agent.ts     chat stream (SSE)
    │   └── mock/        data contoh, tidak masuk jalur produksi
    ├── components/
    │   ├── base/        Icon · Button · Card · Badge · Table · Flyout · Window
    │   ├── shell/       BootScreen · SignIn · Taskbar · Clock · Desktop
    │   ├── agent/       AgentPanel · AgentMessage · AgentTrace · AgentComposer
    │   └── module/      ModuleWindow · ModuleCards · DocList
    ├── views/           LoginView · RegisterView · PendingView · DesktopView
    ├── styles/          tokens.css · base.css
    └── types/index.ts
```

Folder kerja bernama `desk/` selama migrasi. Setelah paritas, `frontend/` (Next.js) dihapus dan `desk/` di-*rename* menjadi `frontend/`.

---

## 10. Kontrak API Desktop

| Endpoint | Isi |
|---|---|
| `GET /api/method/aios_v1.api.desktop.bootstrap` | `user{id,name}`, `company{id,name,currency}`, `agents[]`, `modules[]`, `csrf_token` |
| `GET /api/method/aios_v1.api.desktop.module` | `module`, `cards[]`, `doctypes[]`, `rows[]`, `pagination` (`page`, `page_size`, `total`, `total_pages`); menerima `module`, `page`, `page_size`, `filters` JSON (`date_from`, `date_to`, `status`, `party` sesuai allowlist modul) |
| `GET /api/method/aios_v1.api.desktop.list` | `module`, `doctype`, `rows[]`, `pagination`; menerima `module`, `doctype`, `page`, `page_size`, `filters` |
| `GET /api/method/aios_v1.api.desktop.search` | `results[]` berisi item modul (`type: "module"`, `module`) dan dokumen (`type: "document"`, `module`, `doctype`, `name`, `row`) yang di-scope ke company aktif; di UI (`desk/src/api/modules.ts`) dinormalisasi menjadi `SearchResult` (`kind: "module" \| "document"`), klik item modul maupun dokumen membuka jendela `module:<key>` |
| `GET /api/method/aios_v1.api.desktop.settings` | `profile{name,persona,status}`, `company{id,name,currency}`, `quota{limit,used,remaining,percent_used}`, `reset{at,at_label,seconds_remaining,source,scheduler_active}`; baca-saja untuk `AIOS Client` aktif tanpa mengekspos field rahasia `AIOS Setting` |
| `POST /api/chat/<branch>/stream` | stream SSE; memakai ulang dispatcher `/stream`; request membawa `file_ids[]` opsional untuk lampiran; mendukung event kontrol UI `{"type": "open_module", "module": "<key>"}` dari manager |
| `POST /api/chat/upload` | multipart `file` + `conversationId` (atau `branch` bila belum ada conversation); membuat Private `File` awalnya terikat conversation; respons `conversationId` + metadata `attachment` — H5 fase 1 |

Backend memvalidasi setiap ID pada `file_ids` sebagai Private `File` milik session user dan terkait ke conversation chat yang sama; ukuran dan format harus dalam batas yang diizinkan. File tidak valid ditolak sebelum konteks model dibentuk. Setelah pesan user disimpan, attachment dipindahkan secara relasional ke `AIOS Message` lewat field attachment bawaan Frappe; file keluaran agent ditautkan ke pesan agent. Ini tidak menambah schema dan tidak memindahkan isi file. `attachment.id` pada respons upload hanya state internal frontend untuk mengirim `file_ids`: tidak ditampilkan ke user, tidak diketik user, dan tidak boleh muncul di pesan error maupun event `artifact_created`. Client tidak pernah menerima isi file melalui metadata maupun pesan error.

Semua endpoint memakai sesi Frappe yang sedang login dan tunduk pada `docs/03` §2.2. Tidak ada kredensial layanan di jalur ini.

---

## 11. Halaman yang Diport

| Halaman lama | Nasib |
|---|---|
| Login | Diport |
| Register (pendaftaran mandiri) | Diport |
| Pending provisioning | Diport |
| Workspace (`/home`) | Diganti desktop |
| Settings (kuota, persona, status) | **Masuk desktop** sebagai jendela Pengaturan |
| Onboarding koneksi DB | **Tidak diport** — adapter DB eksternal dihapus (`docs/03` §2) |
| Payment | **Tidak diport** — sudah mati |
| Dashboard developer | **Diport setelah `#11`**, bukan sekarang |

---

## 12. Batasan yang Diakui

1. **Belum ada isolasi level OS.** UI berjalan di browser; keamanan tetap di lapisan server (`docs/02` §2.3).
2. **Modul belum punya penulisan.** Semua aksi tulis lewat approval.
3. **Dashboard developer belum dibangun** — menunggu backend `#11`.
