# 08 — Desain Ekasa Desk (Antarmuka Desktop OS)

Dokumen ini menetapkan desain antarmuka klien AIOS: **Ekasa Desk**, sebuah *desktop OS* di browser. Sifatnya **normatif** — kode menyesuaikan dokumen ini.

> **Sumber kebenaran visual: `ekasa-desk-prototype/index.html`.** Prototype yang dibuat owner adalah **acuan tampilan**, bukan sekadar referensi. Dokumen ini menurunkan tata letak, komposisi, dan hierarki visual dari prototype tersebut; yang berubah hanyalah bahan (data nyata menggantikan mock) dan disiplin penulisan kode (nol hardcoded, token visual). Bila dokumen ini dan prototype berbeda dalam hal **susunan atau elemen yang tampak**, prototype yang menang dan dokumen ini harus dikoreksi — bukan sebaliknya. Prototype bukan acuan untuk cara menulis kode: ia satu berkas HTML dengan data mock dan warna hex inline, dan pola itu **dilarang** di `frontend/` (§7, §8).

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

Layar penuh dengan progres bertahap yang mengikuti tema aktif (`--boot-*`): menyambung ke site, memulihkan sesi, mengambil `frappe.boot`, memuat workspace & izin, mendaftarkan agent, membuka kanal realtime, menyiapkan desktop. Progres harus mencerminkan langkah nyata, bukan animasi palsu.

### 2.2. Sign-In

Form email + password, ditambah tautan ke pendaftaran mandiri. Kegagalan menampilkan pesan aman (tanpa detail internal). Setelah sukses, lanjut ke desktop sesuai peran.

### 2.3. Desktop

- **Ikon desktop** (kiri atas, grid vertikal): **bidang ERP** (`Sales`, `Finance`, dst sesuai bidang aktif dari `modules.domains`) dengan tile besar (`.tile.xl`) berwarna `var(--domain-*)` + label di bawah, digabung bersama AI Agents, Files, dan Tentang AIOS (`Classic Desk` tidak dibuat — §12 butir 4). Pola visual dari prototype: `.desk-icons` (`display:grid; grid-auto-flow:row; gap:6px; width:88px`) dan `.desk-icon` (ikon 48px, label 12px, `border-radius:8px`, state `.sel` memakai `--accent-soft` + border `--accent`). Klik tunggal memilih ikon (state `.sel`); klik-ganda atau Enter membuka; pada layar sempit atau perangkat sentuh (`.os.narrow` / `pointer: coarse`) klik tunggal langsung membuka.
- **Jendela bidang**: membuka satu bidang menampilkan **kartu KPI** + **shortcut modul** + kartu "tanya agent" — diimplementasikan di `frontend/src/components/domain/DomainWindow.vue` (fase 3d-2, lihat §6).
- **Taskbar** di bawah: tiga kolom (`1fr auto 1fr`). Kiri: nama site + status. Tengah: tombol mulai, pencarian, tombol agent, tombol app yang sedang berjalan. Kanan: lonceng peringatan kanal (bell dengan badge hitungan total flag `Open` + total pesanan belum dibaca dari server, dibatasi `99+`), status koneksi, jam + tanggal. Tombol app memakai tile berwarna bidang.
- **Flyout**: pencarian (`Ctrl+K`), daftar agent (`Ctrl+J`), dan notifikasi. `Esc` menutup. Semua flyout muncul dari taskbar (`bottom: calc(var(--taskbar-h) + 10px)`), lebar `min(660px, 100% - 16px)`, sudut 14px.
- **Start Menu** (§2.5): pencarian → **grid bidang** (`.mod-grid` 7 kolom) → AI agents → footer profil + tombol pengaturan + daya (Recent belum memiliki backend sehingga tidak dirender).
- **Tema**: tiga opsi — `Automatic` (*Ikuti sistem*, default; menghapus atribut `data-theme` pada `<html>` sehingga mengikuti `prefers-color-scheme`), `Light` (`data-theme="light"`), dan `Dark` (`data-theme="dark"`). Preferensi disimpan di field bawaan Frappe `User.desk_theme` lewat endpoint `frappe.core.doctype.user.user.switch_theme` dan dibaca dari `desktop.settings` (`theme.value`, `theme.options`). Saat boot (`main.ts`), `localStorage` (`aios.desk.theme`) dibaca semata-mata untuk menghilangkan kedipan awal; `User.desk_theme` dari server tetap menjadi sumber kebenaran dan menimpa cache bila berbeda.

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

### 2.5. Start Menu

Susunan dari atas ke bawah, sesuai prototype:

1. **Tombol pencarian** selebar flyout, ikon + teks + `kbd` `Ctrl K`.
2. **Grid bidang** — header `Bidang` + jumlah bidang aktif, lalu `.mod-grid` (`display:grid; grid-template-columns:repeat(7,1fr); gap:4px`) berisi tombol `.mod` (tile 44px `.tile.lg` dengan background `var(--domain-*)`, label 12px di bawah, `flex-direction:column`, `align-items:center`). Klik tombol bidang langsung memanggil `modules.openDomain(key)`. **Ini bukan pill agent** — memakai grid bidang tersendiri; blok pill modul lama telah dipindahkan sepenuhnya ke dalam jendela bidang.
3. **AI agents** — deretan pill (`.agent-pill`) dengan titik warna per cabang (`.agent-dot`).
4. **Recent** — dua kolom di prototype (tile + nama dokumen + subteks). **Status:** saat ini belum ada endpoint backend untuk riwayat dokumen/Recent, sehingga section ini tidak dirender di UI untuk mencegah data rekaan/palsu.
5. **Footer** — avatar + nama + peran · site; di kanan tombol Pengaturan dan tombol daya (Kunci / Muat ulang / Keluar).

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

File yang dibuat agent disimpan sebagai Private `File` (`docs/02` §3.2) dan tampil sebagai **berkas di desktop**. Approval Card H4 adalah event backend virtual; UI #12 fase 2a mengambil detail dari `get_draft` (jendela kartu dengan Setujui/Tolak, termasuk hasil gagal `executed:false` yang dijelaskan dengan code+message), daftar draft pending milik pemilik lewat `list_pending_drafts`, dan kartu tidak membuat `File`. Daftar draft pending di jendela `PendingDraftsWindow` menampilkan status memuat, daftar kartu, dan kondisi kosong ("Tidak ada draft yang menunggu persetujuan.") hanya bila pemanggilan berhasil; bila pemanggilan gagal, error tidak ditelan melainkan ditampilkan sebagai banner `role="alert"` dengan tombol coba lagi, dilaporkan ke DocType `Error Log` via `log_client_error`, serta memunculkan badge indikator `!` di header Agent Panel (#12 fase 3d-2c):

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

## 6. Bidang, Modul & Jendela

### 6.1. Dua lapis: bidang lalu modul

Tampilan mengikuti prototype yang memakai **dua lapis**, dan keduanya tidak boleh dicampur:

1. **Bidang** (*domain*) — kelompok kerja tingkat atas, mis. `Sales`, `Finance`, `Inventory`, `Reports`. Satu bidang = satu ikon desktop + satu entri grid di Start Menu. Membuka bidang menampilkan **jendela bidang** berisi kartu KPI, daftar shortcut modul, dan kartu "tanya agent". Ini yang digambarkan prototype sebagai *workspace* ERPNext (`Accounting`, `Selling`, `Stock`, dst).
2. **Modul** — daftar dokumen satu DocType di dalam bidang, mis. `Sales Invoice` di dalam `Sales`. Klik shortcut membuka tampilan daftar; breadcrumb kembali ke bidang.

Jendela bidang (window ID `domain:<key>`, diimplementasikan di `frontend/src/components/domain/DomainWindow.vue`) merender:
- **Header ringkas**: ikon bidang + label + subteks "Bidang · Baca saja" + tombol refresh (`.domain-refresh`).
- **Kartu KPI** (`.domain-cards`, grid `auto-fit minmax(170px, 1fr)`): tiap kartu (`.domain-card`) berisi label (`.domain-card-label`) dan nilai angka (`.domain-card-value`). Angka dihitung **server** via agregat `desktop.domain()`, klien hanya memformat (angka pemisah ribuan atau mata uang dengan currency response).
- **Shortcut** (`.domain-shortcuts`): satu tombol per modul anggota (`.domain-shortcut`), berisi ikon + label + jumlah baris dokumen (`row_count`), klik memanggil `modules.openModule(key)` untuk membuka jendela modul yang sudah ada.
- **Kartu agent** (`.domain-ask`): titik inisial agent pemilik bidang (`.agent-dot`) + nama agent + dua saran prompt (`.chip`); klik prompt langsung mengirim pesan ke agent terkait dan membuka panel chat, atau klik "Tanya agent" membuka panel chat di cabang tersebut.

Jendela modul (window ID `module:<key>`) mempertahankan kontrak yang sudah ada: header + refresh, form filter sesuai deklarasi backend (`date_from`, `date_to`, `status`, `party`), tabel kolom dari server, navigasi halaman.

### 6.2. Katalog server-owned

Daftar bidang dan modul berasal dari backend (§7), bukan dari komponen. Katalog modul ada di `aios_v1/lib/desktop_modules.py` (7 modul: `sales_invoice`, `sales_order`, `purchase_invoice`, `payment_entry`, `customer`, `supplier`, `item`); definisi bidang beserta KPI-nya ada di `aios_v1/lib/desktop_domains.py` (11 bidang ERP). Setiap bidang menyatakan: `key`, `label`, `icon`, `color_token` (nama token mis. `domain-sales`, bukan hex — §8), `status` (`"active"` | `"planned"`), daftar modul anggota (`modules`), dan definisi KPI (`cards`: `key`, `label`, `aggregate`, `doctype`, `field`, `format`, `filters`).

- **Dua tier (`active` vs `planned`):** `sales` dan `finance` berstatus `"active"` dengan modul anggota dan kartu KPI penuh. Sembilan bidang ERP lain (`purchasing`, `inventory`, `manufacturing`, `projects`, `crm`, `assets`, `support`, `quality`, `accounting`) terdaftar di katalog dengan `status: "planned"`, `modules: ()`, dan `cards: ()`.
- **Aturan `planned` tidak dirender:** `get_domain_catalog()` (yang dikirim di `desktop.bootstrap().domains`) dan `get_domain_keys()` (yang dipakai enum tool `open_domain`) **hanya** mengembalikan bidang berstatus `"active"`. Bidang `"planned"` tidak dikirim ke UI, tidak dirender di desktop maupun Start Menu, tidak dievaluasi KPI-nya, dan ditolak oleh `desktop.domain()` dengan `ValidationError`. Membuka bidang baru di masa depan cukup mengubah `status` menjadi `"active"` serta mengisi `modules` dan `cards` di server tanpa perubahan kode frontend.

Bidang dibuka dari ikon desktop, grid Start Menu, pencarian (`Ctrl+K`), **atau** oleh agent ("buka Sales" → tool `open_domain` → event SSE `open_domain` → membuka jendela `domain:<key>`). Modul tetap dibuka lewat tool `open_module` → event SSE `open_module` → jendela `module:<key>`. Jendela bidang di-host di `WindowHost.vue` lewat `<DomainWindow :domain-key="w.id.slice(7)" />` (fase 3d-2).

### 6.3. Aturan angka

Kartu KPI adalah agregat yang dihitung server (`COUNT`/`SUM`), bukan dihitung di browser. Tidak ada jalur yang menembus izin: KPI dihitung dengan izin user yang sedang login (`frappe.get_list`), dan bila sebuah DocType tidak boleh dibaca user tersebut, KPI-nya tidak boleh ditampilkan. Tidak ada `ignore_permissions` untuk KPI.

Modul dan bidang bersifat **baca saja**. Penulisan tetap lewat approval.

### 6.4. Jendela Pengaturan (*Settings*)

Jendela **Pengaturan** (`frontend/src/components/windows/SettingsWindow.vue`, window ID `settings`, dibuka dari Start Menu) memiliki tata letak 2 kolom: menu navigasi kiri (`168px`) dengan 3 tab (**Umum** dengan ikon `gear`, **Konektor** dengan ikon umum `link`, **Personalisasi** dengan ikon `sparkle`) beserta tombol muat ulang pengaturan di kiri bawah, dan panel konten kanan (`role="tabpanel"`) dengan scroll mandiri. Judul jendela tidak diduplikasi di dalam area konten window. Saat jendela di-maximize, tata letak mengikuti layar penuh (full screen 100% viewport) tanpa batas lebar (`max-width: none`). Seluruh tombol aksi di dalam jendela menggunakan tombol ikon minimalis (`AppIcon`, border tipis, latar surface seragam) yang dilengkapi `title` dan `aria-label` eksplisit untuk aksesibilitas keyboard dan pembaca layar.

- **Tab Umum:**
  - **Profil pengguna:** `name` (`User.full_name` atau `user`), `persona` (`User.aios_persona`), dan `status` (`User.aios_status`).
  - **Tema tampilan:** kontrol radio berbasis ikon (`Ikuti sistem` dengan ikon `desk`, `Terang` dengan ikon `sun`, `Gelap` dengan ikon `moon`) yang di-render dari `data.theme.options` (`["Automatic", "Light", "Dark"]`). Perubahan tema memanggil `POST /api/method/frappe.core.doctype.user.user.switch_theme` dengan header `X-Frappe-CSRF-Token`; bila gagal, menampilkan banner status error tanpa mengubah `data.theme.value` maupun atribut `data-theme`.
  - **Company aktif:** `name` dan `currency` dari company tingkat site (`AIOS Setting.default_company` / `Global Defaults`).
  - **Kuota site:** menampilkan plafon tingkat site (`AIOS Setting.site_token_limit` dan `site_tokens_used`, bukan per user) dengan label eksplisit **Kuota site**, progress bar (`percent_used`, dibatasi 100% untuk lebar bar), nilai `terpakai / limit`, serta `remaining` (bernilai `null` bila `limit <= 0`).
  - **Jadwal reset kuota site:** waktu reset berikutnya diambil server dari method internal Frappe `ScheduledJobType.get_next_execution()` untuk job `aios_v1.services.usage.reset_daily_counters`. Server menghitung `seconds_remaining` (`int`) dan `at_label` (`HH:mm`). Bila hitung mundur mencapai `0`, UI menampilkan **"Menunggu reset berikutnya"**. Bila scheduler tidak aktif atau job tidak ditemukan, UI menampilkan peringatan **"Reset belum terjadwal"**.
- **Tab Konektor:**
  - Diwakili oleh ikon konektor umum `link` pada menu kiri.
  - Menampilkan kartu **Integrasi Telegram** (dipindahkan dari kartu bertumpuk lama ke tab terisolasi).
  - Status tersambung menampilkan `@username` staf/ID Telegram dengan tombol aksi ikon `unlink` (**Putuskan Tautan**).
  - Status belum tersambung menampilkan instruksi penautan dengan tombol aksi ikon `telegram` (**Hubungkan ke Telegram**), tombol ikon `copy` (**Salin Tautan**, berubah jadi ikon `check` saat tersalin), dan tombol ikon `external-link` (**Buka Telegram Langsung**).
- **Tab Personalisasi:**
  - Menampilkan kartu **Konteks Perusahaan** yang memetakan field `AIOS Setting.company_context_persona` (`Small Text`, dibatasi maksimal 2000 karakter).
  - Menyediakan area teks multi-baris (`textarea`) tanpa subjudul deskripsi kartu yang redundan, dengan counter karakter real-time `X / 2000 karakter`, indikator status simpan ("Menyimpan...", "Tersimpan", "Gagal menyimpan"), tombol aksi ikon `check` (**Simpan**, seragam 32×32 px border line latar surface, aktif hanya bila ada perubahan/dirty dan valid), serta tombol aksi ikon `x` (**Batalkan perubahan**).
  - Teks ini menjadi knowledge base dasar perusahaan yang disuntikkan ke seluruh agen AI di site tersebut.
  - Pengubahan disimpan oleh client melalui endpoint sempit `POST /api/method/aios_v1.api.desktop.save_company_persona`.
- **Kerahasiaan `AIOS Setting`:** endpoint `desktop.settings` hanya membaca field yang diizinkan untuk antarmuka pengguna (`site_token_limit`, `site_tokens_used`, `company_context_persona`); field sensitif/konfigurasi internal backend (`api_key`, `system_ethos`, `model_name`, `base_url`, `temperature`) tetap terlarang keras dan tidak pernah disertakan dalam respons maupun direferensikan di komponen UI.
- **Adapter API (`@modules-api`):** pemilihan adapter dilakukan saat build di `frontend/vite.config.ts` lewat `VITE_DESKTOP_ADAPTER=real|mock` (default `real`), di mana `frontend/src/api/modules.ts` dan `frontend/src/api/mock/modules.ts` keduanya memenuhi kontrak TypeScript `ModulesApi` (`satisfies ModulesApi`) mencakup fungsi `saveCompanyPersona`.

---

## 7. Aturan *Zero Hardcoded*

| Data | Sumber |
|---|---|
| Daftar agent, nama, deskripsi, saran prompt | Backend (`registry.py`) |
| Daftar bidang, label, ikon, nama token warna, modul anggota, definisi KPI | Backend (`aios_v1/lib/`, satu sumber dengan katalog modul) |
| Daftar modul, ikon, doctype, kolom, filter, kartu | Backend |
| Company aktif, mata uang | `AIOS Setting` |
| Kuota & pemakaian token | `AIOS Setting.site_token_limit` (gerbang), `User.aios_tokens_used` (statistik) |
| Versi & URL API | `frappe.boot` / environment |

**Aturan yang bisa diuji:** tidak ada nama agent, nama bidang, nama modul, atau nama doctype yang ditulis sebagai teks di berkas komponen. Data contoh hanya boleh hidup di lapisan `api/mock/` dan tidak pernah diimpor jalur produksi.

**Warna bidang tidak dikirim sebagai hex.** Prototype menulis `color:'#1F8A70'` inline; di `frontend/` itu dilarang (§8). Backend mengirim **nama token** (mis. `domain-sales`), dan komponen memetakannya ke `var(--domain-sales)`. Token nilainya didefinisikan sekali di `tokens.css`.

Endpoint `/api/branches` memproyeksikan data di server untuk tampilan saja: cabang mengirim `key`, `name`, `description`, `tagline`, `enabled`; worker mengirim `key`, `branch`, `jobRole`, `description`, `exampleQuestions`, `enabled`. Materi prompt internal tidak pernah dikirim ke browser.

**Aturan yang sama berlaku untuk gaya:** komponen dilarang menulis warna, font, bayangan, atau radius secara langsung. Semua lewat token (§8).

---

## 8. Token Visual & CSS

**Aturan mutlak:** nilai visual hanya boleh ditulis di `frontend/src/styles/tokens.css`. Berkas `base.css` maupun komponen `.vue` dilarang menulis literal warna, ukuran font, ketebalan font, radius, spacing, z-index, durasi transisi/animasi, efek blur kaca, atau lebar panel — semuanya wajib mereferensikan `var(--token)`.

Dua lapis token di `styles/tokens.css`:

1. **Primitives & skala terukur** — nilai mentah (hex, rgba, px, ms/s, font) yang hanya boleh didefinisikan di `tokens.css`:
   - **Font family:** `--font-ui`, `--font-mono`.
   - **Spacing (`padding`/`margin`/`gap`):** `--space-{1,2,3,4,5,6,7,8,9,10,11,12,13,14,16,18,20,24,28,29}`.
   - **Radius:** `--radius-{3,4,5,6,8,9,10,12,13,14,20}`, `--radius-pill` (`999px`), `--radius-circle` (`50%`), `--radius-window-foot` (`0 0 14px 14px`).
   - **Ukuran font:** `--fs-{10,11,11-5,12,12-5,13,13-5,14,14-5,15,17,18,20,24,30}`.
   - **Ketebalan font:** `--fw-{400,500,600,700,800}`.
   - **Z-index:** `--z-base` (`1`), `--z-raised` (`2`), `--z-taskbar` (`50`), `--z-panel` (`55`), `--z-flyout` (`60`), `--z-toast` (`70`).
   - **Durasi:** `--dur-{12,15,18,20,22,30,40,45,50,90}` (`0.12s`…`0.9s`), `--dur-100` (`1s`), `--dur-110` (`1.1s`), `--dur-240` (`2.4s`), `--dur-instant` (`0.01ms`).
   - **Glass blur (`backdrop-filter` & `-webkit-backdrop-filter`):** `--glass-blur-sm` (`blur(24px) saturate(1.3)`), `--glass-blur-md` (`blur(26px) saturate(1.4)`), `--glass-blur-lg` (`blur(30px) saturate(1.4)`).
   - **Dimensi shell:** `--taskbar-h` (`52px`), `--panel-w` (`410px`).
2. **Semantic & tema** — `--wall-base`, `--wall-1..3`, `--glass`, `--glass-strong`, `--glass-line`, `--surface`, `--surface-2`, `--line`, `--fg`, `--muted`, `--faint`, `--accent`, `--accent-strong`, `--accent-soft`, `--on-accent`, `--ok`, `--ok-soft`, `--warn`, `--warn-soft`, `--bad`, `--bad-soft`, `--hover`, `--press`, `--shadow`, `--shadow-sm`, `--agent-accent-*`, token warna 11 bidang (`--domain-sales`, `--domain-finance`, `--domain-purchasing`, `--domain-inventory`, `--domain-manufacturing`, `--domain-projects`, `--domain-crm`, `--domain-assets`, `--domain-support`, `--domain-quality`, `--domain-accounting`), serta token layar boot yang mengikuti tema (`--boot-bg`, `--boot-fg`, `--boot-bar`, `--boot-status`, `--boot-log`, `--boot-log-ok`, `--boot-skip`) lengkap di `:root`, `@media (prefers-color-scheme: dark) :root:not([data-theme='light'])`, `:root[data-theme='dark']`, dan `:root[data-theme='light']`.

Yang **tidak** perlu token: nilai sekali pakai seperti lebar kolom tabel di satu tempat, serta nilai struktural `0`, `auto`, `100%`, dan `1px` pada `border: 1px solid var(--line)`.

**Pemeriksaan otomatis:** `aios_v1/tests/test_frontend_no_hardcode.py` memindai `frontend/src/components/{module,domain,shell,windows}` dan `frontend/src/styles/base.css` (mengecualikan `styles/tokens.css` sebagai sumber kebenaran) terhadap warna literal hex/rgb/rgba.

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
frontend/
├── index.html
├── vite.config.ts
├── tsconfig.json
└── src/
    ├── main.ts
    ├── App.vue
    ├── router/index.ts
    ├── stores/          session · agents · modules · conversations · ui
    ├── api/
    │   ├── client.ts    apiFetch + CSRF + pesan aman
    │   ├── modules.ts   bootstrap · domain · module · list · search · settings
    │   ├── chat.ts      chat stream (SSE)
    │   └── mock/        data contoh, tidak masuk jalur produksi
    ├── components/
    │   ├── base/        AppIcon · EkasaMark · RichText · Toasts
    │   ├── shell/       BootScreen · Taskbar · StartMenu · SearchFlyout · WindowHost
    │   ├── agent/       AgentPanel · AgentStep
    │   ├── domain/      DomainWindow · DomainCards · DomainShortcuts
    │   ├── module/      ModuleWindow
    │   └── windows/     SettingsWindow · FilesWindow · ArtifactWindow · ApprovalCardWindow · PendingDraftsWindow · AboutWindow
    ├── views/           LoginView · RegisterView · PendingView · DesktopView
    ├── styles/          tokens.css · base.css
    └── types/index.ts
```

**Selisih yang disengaja terhadap prototype:** prototype adalah satu berkas HTML dengan data mock dan warna hex inline. `frontend/` memisahkan komponen, mengambil semua data dari backend, dan memakai token visual (§7, §8). Yang **tidak boleh berbeda** adalah susunan dan elemen yang tampak.

---

## 10. Kontrak API Desktop

| Endpoint | Isi |
|---|---|
| `GET /api/method/aios_v1.api.desktop.bootstrap` | `user{id,name}`, `company{id,name,currency}`, `agents[]`, `domains[]` (hanya bidang `active`: `{key,label,icon,color_token,module_count}`), `modules[]`, `csrf_token` |
| `GET /api/method/aios_v1.api.desktop.domain` | `domain{key,label,icon,color_token}`, `company{id,name,currency}`, `cards[{key,label,value,format,currency?}]`, `modules[{key,label,icon,row_count}]`; menerima `domain` (hanya bidang `active`; KPI & `row_count` dihitung via `frappe.get_list` dengan izin user login tanpa `ignore_permissions`) |
| `GET /api/method/aios_v1.api.desktop.module` | `module`, `cards[]`, `doctypes[]`, `rows[]`, `pagination` (`page`, `page_size`, `total`, `total_pages`); menerima `module`, `page`, `page_size`, `filters` JSON (`date_from`, `date_to`, `status`, `party` sesuai allowlist modul) |
| `GET /api/method/aios_v1.api.desktop.list` | `module`, `doctype`, `rows[]`, `pagination`; menerima `module`, `doctype`, `page`, `page_size`, `filters` |
| `GET /api/method/aios_v1.api.desktop.search` | `results[]` berisi item modul (`type: "module"`, `module`) dan dokumen (`type: "document"`, `module`, `doctype`, `name`, `row`) yang di-scope ke company aktif; di UI (`frontend/src/api/modules.ts`) dinormalisasi menjadi `SearchResult` (`kind: "module" \| "document"`), klik item modul maupun dokumen membuka jendela `module:<key>` |
| `GET /api/method/aios_v1.api.desktop.settings` | `profile{name,persona,status}`, `company{id,name,currency}`, `quota{limit,used,remaining,percent_used}`, `reset{at,at_label,seconds_remaining,source,scheduler_active}`, `theme{value,options}`; baca-saja untuk `AIOS Client` aktif tanpa mengekspos field rahasia `AIOS Setting` (`User.desk_theme` kosong/invalid dinormalisasi ke `"Automatic"`, perubahan tema ditulis lewat `POST /api/method/frappe.core.doctype.user.user.switch_theme`). Jendela `SettingsWindow.vue` menampilkan 3 tab dasar (`Umum`, `Konektor`, `Personalisasi`) plus 2 tab khusus pemegang Role `AIOS Client Owner`: `Penerima Kanal` dan `Kelola Staf` |
| `GET /api/method/aios_v1.api.desktop.client_staff_and_recipients` | Khusus `AIOS Client Owner` aktif; mengembalikan `users[{email,full_name,persona,aios_status,enabled,is_owner,is_receiver}]` dan `quota{active_users,max_users,remaining_slots}` |
| `POST /api/method/aios_v1.api.desktop.set_channel_receiver` | Khusus `AIOS Client Owner` aktif; menerima `{target_user, is_receiver}`; memasang/mencopot `AIOS Channel Receiver Profile` pada staf `AIOS Client` aktif |
| `POST /api/method/aios_v1.api.desktop.create_client_staff` | Khusus `AIOS Client Owner` aktif; menerima `{full_name, email, persona}`; memeriksa plafon `AIOS Setting.max_users`, membuat `User` (`AIOS Client Profile`, `aios_status = "Active"`), dan mengembalikan `invitation_url` sekali pakai (`/update-password?key=...`, 20 menit) yang dinormalisasi memuat port webserver site bila non-produksi |
| `POST /api/method/aios_v1.api.desktop.set_client_staff_status` | Khusus `AIOS Client Owner` aktif; menerima `{target_user, status}` (`"Active"` atau `"Suspended"`); menolak menonaktifkan diri sendiri atau sesama `AIOS Client Owner` |
| `POST /api/method/aios_v1.api.desktop.regenerate_client_staff_invite` | Khusus `AIOS Client Owner` aktif; menerima `{target_user}`; menerbitkan ulang `invitation_url` sekali pakai untuk staf `AIOS Client` aktif yang dinormalisasi memuat port webserver site bila non-produksi |
| `POST /api/method/aios_v1.api.desktop.log_client_error` | Menerima `{message: str, context: str, stack: str}`; mencatat error kritis frontend ke DocType `Error Log` lewat `frappe.log_error` dengan sanitasi kredensial/DB/site; dibatasi laju (`@rate_limit(limit=10, seconds=60, methods=["POST"], ip_based=True)`); menolak Guest, mengizinkan user terautentikasi (termasuk Administrator); cakupan sempit: khusus kegagalan data vital (bootstrap gagal, dsb.) |
| `GET /api/method/aios_v1.api.control.health` | Control API token-only; `{status, site, time, version}` |
| `GET /api/method/aios_v1.api.control.users` | Control API token-only; menerima `status`, `page`, `page_size`; selalu memfilter role `AIOS Client` (filter melekat di endpoint, bukan parameter); mengembalikan `users[]` dengan hanya `name`, `full_name`, `aios_status`, `aios_persona`, `enabled`, `last_login`, serta `total`, `page`, `page_size`; mengecualikan `Administrator` dan `Guest` |
| `POST /api/method/aios_v1.api.control.activate_user` | Control API token-only; menerima `user`, `status` (`Active` atau `Suspended`); memperbarui `aios_status` dan `enabled` bersama; mengembalikan `{ok, user, aios_status}` |
| `GET /api/method/aios_v1.api.control.metrics` | Control API token-only; angka agregat `{site_tokens_used, site_token_limit, active_users, total_users, tokens_today}` tanpa isi `AIOS Setting` atau daftar user |
| `POST /api/chat/<branch>/stream` | stream SSE; memakai ulang dispatcher `/stream`; request membawa `file_ids[]` opsional untuk lampiran; mendukung event kontrol UI terpisah `{"type": "open_domain", "domain": "<key>"}` (untuk jendela bidang `domain:<key>`) dan `{"type": "open_module", "module": "<key>"}` (untuk jendela modul `module:<key>`) dari manager |
| `POST /api/chat/upload` | multipart `file` + `conversationId` (atau `branch` bila belum ada conversation); membuat Private `File` awalnya terikat conversation; respons `conversationId` + metadata `attachment` — H5 fase 1 |

Backend memvalidasi setiap ID pada `file_ids` sebagai Private `File` milik session user dan terkait ke conversation chat yang sama; ukuran dan format harus dalam batas yang diizinkan. File tidak valid ditolak sebelum konteks model dibentuk. Setelah pesan user disimpan, attachment dipindahkan secara relasional ke `AIOS Message` lewat field attachment bawaan Frappe; file keluaran agent ditautkan ke pesan agent. Ini tidak menambah schema dan tidak memindahkan isi file. `attachment.id` pada respons upload hanya state internal frontend untuk mengirim `file_ids`: tidak ditampilkan ke user, tidak diketik user, dan tidak boleh muncul di pesan error maupun event `artifact_created`. Client tidak pernah menerima isi file melalui metadata maupun pesan error.

Semua endpoint **Desktop API** memakai sesi Frappe yang sedang login dan tunduk pada `docs/03` §2.2. Control API (`aios_v1.api.control.*`) memakai token `AIOS Control`, bukan sesi, dan dijelaskan di `docs/03` §1.4.

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
| Dashboard developer | **Bukan bagian Ekasa Desk** — app Vue terpisah di `admin/` (app `aios_v1`), dilayani app di `/aios-admin` (`#11` fase 1c-2) |

Paritas visual diukur terhadap `ekasa-desk-prototype/index.html`, bukan terhadap `frontend/` lama. Daftar selisih yang belum tertutup dipelihara di `docs/05.1`.

---

## 12. Batasan yang Diakui

1. **Belum ada isolasi level OS.** UI berjalan di browser; keamanan tetap di lapisan server (`docs/02` §2.3).
2. **Modul belum punya penulisan.** Semua aksi tulis lewat approval.
3. **Dashboard developer** dibangun sebagai **app Vue terpisah `/aios-admin`** (folder `admin/`, API `aios_v1.api.control_plane`, `#11` fase 1c-2) dan **bukan bagian Ekasa Desk**; tab undangan sekali pakai, tombol **Buat Site** (fase 2 `#11`), serta DocPerm/registry plugin `AIOS Admin` menyusul di `#11`.
4. **`Classic Desk` tidak diport.** Prototype menampilkan tombol ke `/app` (Frappe Desk). Di `frontend/` tombol itu **tidak boleh ada**: `AIOS Client` ber-`desk_access=0` dan `Administrator` tidak pernah dipakai jalur produk.
5. **Notifikasi dan Peringatan Kanal telah aktif.** Lonceng (bell) di Taskbar kanan terhubung langsung ke backend untuk menghitung total flag percakapan `Open` (`AIOS Conversation Flag` via `?status=Open`) dan total notifikasi draf pesanan baru belum dibaca (`Notification Log`). Dot bell membatasi tampilan hingga `99+` bila total melebihi 99. Mengklik lonceng membuka jendela `Peringatan Kanal` (`ChannelFlagsWindow.vue`) yang memungkinkan staf meninjau bukti pelanggaran aturan percakapan (hingga 50 flag `Open` terbaru) maupun membuka draf pesanan (`approval:<draft_id>`) serta menandai sudah ditinjau. Antrean pesanan dipaginasi 20 item per halaman dengan tata letak pinned footer (bar pagination menempel di bawah window tanpa scroll, kepala window terkunci di atas, daftar pesanan dan flag scroll mandiri), serta kepala window menampilkan total flag `Open` dan total antrean draf pesanan belum dibaca riil dari server.
6. **Selisih kode vs prototype yang masih terbuka** dicatat di `docs/05.1`, bukan disembunyikan di sini.
